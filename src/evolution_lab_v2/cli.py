"""PowerShell-friendly reference and bounded demographic experiment CLI."""
import argparse
from dataclasses import replace
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc

import numpy as np

from .analysis import analyze
from .artifacts import load_checkpoint, provenance, save_checkpoint, write_json, write_outputs
from .config import Config
from .genetics import choose_distinct_parents
from .model import advance, initialize
from .eco_config import EcoConfig


def read_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EcoConfig.from_dict(data) if isinstance(data, dict) and data.get("model") == "demographic" else Config.from_dict(data)


def simulate(config, directory, resume=None, stop_after=None):
    if isinstance(config, EcoConfig):
        from .eco_io import simulate as eco_simulate
        return eco_simulate(config, directory, resume, stop_after)
    state = load_checkpoint(resume, config) if resume else initialize(config)
    if stop_after is not None and not state.generation <= stop_after <= config.generations:
        raise ValueError("stop-after must be between checkpoint and configured final generation")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "model": "fixed_census_diploid_reference",
                "config": config.to_dict(), "provenance": provenance(),
                "status": "running", "protocol": "E1 neutral reference / Gate 2"}
    if resume:
        manifest["resume"] = {"path": str(Path(resume).resolve()),
                              "sha256": hashlib.sha256(Path(resume).read_bytes()).hexdigest()}
    write_json(directory / "manifest.json", manifest)

    def checkpoint(current):
        save_checkpoint(directory / "checkpoint.npz", current)
        print(f"{directory.name}: generation {current.generation}/{config.generations}", flush=True)

    advance(state, until=stop_after, checkpoint=checkpoint)
    manifest["status"] = "complete" if state.generation == config.generations else "paused"
    return write_outputs(directory, state, manifest)


def validate(config):
    if isinstance(config, EcoConfig):
        from .eco_experiment import validate as eco_validate
        return eco_validate(config)
    checks = []
    def require(condition, description):
        if not condition:
            raise ValueError(f"Validation failed: {description}")

    rng = np.random.Generator(np.random.PCG64(12))
    for count in (1, 2, 4, 8):
        weights = np.ones(50)
        weights[0] = 100000
        groups = choose_distinct_parents(rng, np.arange(50), weights, 128, count)
        require(all(len(set(row)) == count for row in groups), "distinct parent count")
    checks.append("distinct weighted parent sampling: 1/2/4/8 contributors")
    for reproduction in ("clone", "two_parent"):
        cfg = Config(reproduction=reproduction, population_size=30, generations=6,
                     chromosome_lengths=(4, 4), seed=19)
        first, second = advance(initialize(cfg)), advance(initialize(cfg))
        require(first.records == second.records, "deterministic metrics")
        require(np.array_equal(first.genomes, second.genomes), "deterministic genomes")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.npz"
            partial = advance(initialize(cfg), until=3)
            save_checkpoint(path, partial)
            resumed = advance(load_checkpoint(path, cfg))
        require(first.records == resumed.records, "checkpoint metrics replay")
        require(np.array_equal(first.genomes, resumed.genomes), "checkpoint genomes replay")
        checks.append(f"{reproduction}: deterministic and exact checkpoint replay")
    print(json.dumps({"validated_config": config.to_dict(), "checks": checks}, indent=2))


def sweep(config, grid_path, directory, replicates, seed):
    if isinstance(config, EcoConfig):
        from .eco_experiment import run_experiment
        specification = {"name": "demographic_sweep", "base": config.to_dict(),
                         "grid": json.loads(Path(grid_path).read_text(encoding="utf-8")),
                         "replicates": replicates, "master_seed": seed}
        return run_experiment(specification, directory)
    if not 1 <= replicates <= 32 or seed < 0:
        raise ValueError("Pilot sweeps require 1..32 replicates and a nonnegative master seed")
    grid = json.loads(Path(grid_path).read_text(encoding="utf-8"))
    if not isinstance(grid, dict) or not grid or "seed" in grid:
        raise ValueError("Grid must be an object without seed; use the master seed")
    if any(not isinstance(v, list) or not v for v in grid.values()):
        raise ValueError("Each grid value must be a nonempty list")
    if any(len({json.dumps(x, sort_keys=True) for x in v}) != len(v) for v in grid.values()):
        raise ValueError("Duplicate grid values would duplicate observations")
    total_runs = replicates * int(np.prod([len(v) for v in grid.values()]))
    if total_runs > 128:
        raise ValueError("Pilot sweep limit: 128 runs")
    seeds = [int(child.generate_state(1, dtype=np.uint64)[0])
             for child in np.random.SeedSequence(seed).spawn(replicates)]
    scenarios = [Config.from_dict({**config.to_dict(), **dict(zip(grid, values))})
                 for values in itertools.product(*grid.values())]
    work = sum(c.population_size * c.generations * c.loci for c in scenarios) * replicates
    if work > 100_000_000:
        raise ValueError("Pilot sweep limit: 100,000,000 individual-locus generations")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    runs = [{"path": f"scenario_{i:03d}_rep_{j:03d}", "config": replace(c, seed=s).to_dict()}
            for i, c in enumerate(scenarios) for j, s in enumerate(seeds)]
    manifest = {"schema_version": 1, "master_seed": seed, "replicate_seeds": seeds,
                "base_config": config.to_dict(), "grid": grid, "replicates_per_scenario": replicates,
                "pairing": "shared founders within replicate; subsequent streams diverge by mechanism",
                "primary_endpoint": "final_gene_diversity (E1 diagnostic only)",
                "provenance": provenance(), "status": "planned", "runs": runs}
    write_json(directory / "sweep_manifest.json", manifest)
    for run in runs:
        simulate(Config.from_dict(run["config"]), directory / run["path"])
    manifest["status"] = "complete"
    write_json(directory / "sweep_manifest.json", manifest)
    analyze(directory, directory / "analysis.json")
    print(f"PASS: {len(runs)} runs; {directory / 'analysis.json'}")


def benchmark(config, sizes, generations, repeats, output):
    if isinstance(config, EcoConfig):
        from .eco_experiment import benchmark as eco_benchmark
        return eco_benchmark(config, sizes, generations, repeats, output)
    if not 1 <= repeats <= 5:
        raise ValueError("Benchmark repeats must be 1..5")
    configs = [replace(config, population_size=n, generations=generations, reproduction=mode)
               for mode in ("clone", "two_parent") for n in sizes]
    if sum(c.population_size * max(1, c.generations) * c.loci for c in configs) * repeats > 50_000_000:
        raise ValueError("Benchmark exceeds pilot workload limit")
    rows = []
    for cfg in configs:
        durations, peaks = [], []
        for rep in range(repeats):
            tracemalloc.start()
            started = time.perf_counter()
            state = advance(initialize(replace(cfg, seed=cfg.seed + rep)))
            durations.append(time.perf_counter() - started)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
            if state.generation != cfg.generations:
                raise ValueError("Benchmark did not complete")
        row = {"config": cfg.to_dict(), "repeats": repeats, "seconds": durations,
               "median_seconds": statistics.median(durations), "peak_traced_bytes": max(peaks)}
        rows.append(row)
        print(f"{cfg.reproduction} N={cfg.population_size}: median {row['median_seconds']:.4f}s", flush=True)
    report = {"provenance": provenance(), "scope": "initialization + reference kernel + metrics + parentage in RAM; tracemalloc enabled; excludes disk I/O",
              "scaling": "No large-run authorization or validated extrapolation; sampler is O(N^2) per generation. Replace/profile before scale-up.", "results": rows}
    write_json(output, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "simulate", "sweep", "benchmark"):
        child = sub.add_parser(command)
        child.add_argument("--config", type=Path)
        if command == "simulate":
            child.add_argument("--output", type=Path, required=True)
            child.add_argument("--resume", type=Path)
            child.add_argument("--stop-after", type=int)
        elif command == "sweep":
            child.add_argument("--grid", type=Path, required=True)
            child.add_argument("--output", type=Path, required=True)
            child.add_argument("--replicates", type=int, default=4)
            child.add_argument("--seed", type=int, default=20261020)
        elif command == "benchmark":
            child.add_argument("--sizes", default="100,500,1000")
            child.add_argument("--generations", "--steps", dest="generations", type=int, default=10)
            child.add_argument("--repeats", type=int, default=3)
            child.add_argument("--output", type=Path, required=True)
    child = sub.add_parser("analyze")
    child.add_argument("--input", type=Path, required=True)
    child.add_argument("--output", type=Path, required=True)
    child = sub.add_parser("experiment")
    child.add_argument("--config", type=Path, required=True)
    child.add_argument("--output", type=Path)
    child.add_argument("--plan-only", action="store_true")
    child.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "experiment":
            from .eco_experiment import run_experiment
            specification = json.loads(args.config.read_text(encoding="utf-8"))
            if not args.plan_only and args.output is None:
                raise ValueError("experiment requires --output unless --plan-only")
            run_experiment(specification, args.output, args.resume, args.plan_only)
            return 0
        if args.command == "analyze":
            manifest = json.loads((args.input/"sweep_manifest.json").read_text(encoding="utf-8"))
            if manifest.get("model") == "demographic":
                from .eco_analysis import analyze as eco_analyze
                eco_analyze(args.input, args.output)
            else:
                analyze(args.input, args.output)
            print(f"Analysis: {args.output}")
            return 0
        config = read_config(args.config) if args.config else Config()
        if args.command == "validate":
            validate(config)
        elif args.command == "simulate":
            simulate(config, args.output, args.resume, args.stop_after)
        elif args.command == "sweep":
            sweep(config, args.grid, args.output, args.replicates, args.seed)
        else:
            sizes = [int(x) for x in args.sizes.split(",")]
            if not sizes:
                raise ValueError("Provide at least one benchmark size")
            benchmark(config, sizes, args.generations, args.repeats, args.output)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0
