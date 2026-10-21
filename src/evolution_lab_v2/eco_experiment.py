"""Planned, resumable demographic experiments and small performance gates."""
from dataclasses import replace
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc
import uuid

import numpy as np

from .artifacts import provenance, signature, write_json
from .eco_config import EcoConfig, STRATEGIES
from .eco_io import load_checkpoint, save_checkpoint, simulate, write_outputs
from .ecology import advance, initialize, state_digest


def plan_experiment(specification):
    allowed = {"name", "base", "grid", "replicates", "master_seed", "experiment_kind", "introduced_strategy"}
    if not isinstance(specification, dict) or set(specification)-allowed:
        raise ValueError("Unknown experiment specification fields")
    base = EcoConfig.from_dict(specification["base"])
    name = specification.get("name", "demographic_comparison")
    kind = specification.get("experiment_kind", "established")
    if kind not in ("established", "isolated", "introduced_modifier"):
        raise ValueError("Unknown experiment_kind")
    introduced = specification.get("introduced_strategy")
    if kind == 'introduced_modifier' and introduced not in STRATEGIES:
        raise ValueError("Specify introduced_strategy for an introduction experiment")
    if kind != 'introduced_modifier' and introduced is not None:
        raise ValueError("introduced_strategy requires an introduction experiment")
    replicates, seed = specification.get("replicates", 8), specification.get("master_seed", 20261020)
    if not isinstance(name, str) or not 1 <= len(name) <= 100:
        raise ValueError("Experiment name must contain 1..100 characters")
    if type(replicates) is not int or not 1 <= replicates <= 32 or type(seed) is not int or seed < 0:
        raise ValueError("Require 1..32 replicates and a nonnegative integer master_seed")
    grid = specification.get("grid", {})
    if not isinstance(grid, dict) or "seed" in grid or "model" in grid:
        raise ValueError("Grid must be an object without seed or model")
    for values in grid.values():
        if not isinstance(values, list) or not values or len({json.dumps(v, sort_keys=True) for v in values}) != len(values):
            raise ValueError("Grid dimensions must contain unique, nonempty lists")
    scenario_count = math_product(len(v) for v in grid.values())
    if scenario_count*replicates > 2048 or scenario_count > 256:
        raise ValueError("Experiment limit: 256 scenarios and 2048 runs")
    seeds = [int(s.generate_state(1, dtype=np.uint64)[0]) for s in np.random.SeedSequence(seed).spawn(replicates)]
    scenarios = []
    for index, values in enumerate(itertools.product(*grid.values())):
        factors = dict(zip(grid, values))
        cfg = EcoConfig.from_dict({**base.to_dict(), **factors})
        if kind == 'introduced_modifier':
            initial = cfg.initial_counts[STRATEGIES.index(introduced)]
            if not 0 < initial < cfg.establishment_size or sum(cfg.initial_counts) <= initial:
                raise ValueError("Introduction requires a resident and an introduced cohort below the establishment threshold")
        scenarios.append({"id": f"S{index:03d}", "factors": factors, "config": cfg.to_dict()})
    updates = sum(s["config"]["capacity"]*s["config"]["steps"] for s in scenarios)*replicates
    locus_updates = sum(s["config"]["capacity"]*s["config"]["steps"]*sum(s["config"]["chromosome_lengths"]) for s in scenarios)*replicates
    if updates > 50_000_000 or locus_updates > 1_000_000_000:
        raise ValueError("Experiment exceeds bounded comparison workload (50m census ticks / 1b locus ticks)")
    runs = [{"path": f"{scenario['id']}_R{rep:03d}", "scenario": scenario["id"],
             "config": {**scenario["config"], "seed": rep_seed}}
            for scenario in scenarios for rep, rep_seed in enumerate(seeds)]
    plan = {"schema_version": 1, "model": "demographic", "name": name,
            "experiment_kind": kind, "introduced_strategy": introduced,
            "specification": specification, "master_seed": seed, "replicate_seeds": seeds,
            "signature": signature(), "primary_endpoint": "introduced_cohort_threshold_crossing_probability" if kind == 'introduced_modifier' else "final_abundance_at_configured_horizon",
            "pairing": "Founders and exogenous environment paired when their parameters agree; other streams diverge with demographics. Parasite tracking is endogenous.",
            "upper_census_ticks": updates, "upper_locus_ticks": locus_updates,
            "scenarios": scenarios, "runs": runs}
    plan["plan_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan


def math_product(values):
    result = 1
    for value in values:
        result *= value
    return result


def run_experiment(specification, directory=None, resume=False, plan_only=False):
    from .eco_analysis import analyze, verify_run
    plan = plan_experiment(specification)
    overview = {"scenarios": len(plan["scenarios"]), "runs": len(plan["runs"]),
                "replicates": len(plan["replicate_seeds"]), "upper_census_ticks": plan["upper_census_ticks"],
                "upper_locus_ticks": plan["upper_locus_ticks"], "plan_sha256": plan["plan_sha256"]}
    print(json.dumps(overview, indent=2), flush=True)
    if plan_only:
        return overview
    if directory is None:
        raise ValueError("Experiment requires an output directory")
    directory = Path(directory)
    manifest_path = directory/"sweep_manifest.json"
    if resume:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous["plan_sha256"] != plan["plan_sha256"]:
            raise ValueError("Resume requires the identical plan, source, protocol and runtime")
        plan = previous
    else:
        directory.mkdir(parents=True, exist_ok=False)
        plan.update({"status": "planned", "provenance": provenance()})
        write_json(manifest_path, plan)  # Freeze all intended runs before results.
    plan["status"] = "running"
    write_json(manifest_path, plan)
    started = time.perf_counter()
    elapsed_runs = []
    completed = 0
    for run in plan["runs"]:
        path = directory/run["path"]
        if path.resolve().parent != directory.resolve():
            raise ValueError("Run path must be inside the experiment directory")
        one_started = time.perf_counter()
        try:
            if path.exists() and (path/"summary.json").exists():
                summary = json.loads((path/"summary.json").read_text(encoding="utf-8"))
                if summary.get("complete"):
                    verify_run(path, run, plan["signature"])
                    completed += 1
                    continue
            checkpoint = None
            if path.exists():
                # Preserve the interrupted attempt. Both resolved rename targets
                # have been checked to remain inside this experiment directory.
                backup = directory/f"{run['path']}_interrupted_{uuid.uuid4().hex[:8]}"
                if backup.resolve().parent != directory.resolve():
                    raise ValueError("Invalid interrupted-attempt path")
                path.rename(backup)
                checkpoint = backup/"checkpoint.npz" if (backup/"checkpoint.npz").exists() else None
            summary = simulate(EcoConfig.from_dict(run["config"]), path, resume=checkpoint, quiet=True)
            if not summary["complete"]:
                raise ValueError("Experiment run did not reach a terminal state")
            completed += 1
            duration = time.perf_counter()-one_started
            elapsed_runs.append(duration)
            remaining = (len(plan["runs"])-completed)*statistics.mean(elapsed_runs)
            print(f"[{completed}/{len(plan['runs'])}] {run['path']}: N={summary['total_population']}; {duration:.2f}s; estimated remaining {remaining/60:.1f} min", flush=True)
            write_json(directory/"progress.json", {"status": "running", "completed": completed, "total": len(plan["runs"]),
                                                    "elapsed_seconds": time.perf_counter()-started, "last_run": run["path"]})
        except (Exception, KeyboardInterrupt) as exc:
            write_json(directory/"progress.json", {"status": "interrupted", "completed": completed,
                                                    "run": run["path"], "error": type(exc).__name__+": "+str(exc)})
            raise
    plan["status"] = "complete"
    write_json(manifest_path, plan)
    try:
        analyze(directory)
    except (Exception, KeyboardInterrupt) as exc:
        write_json(directory/"progress.json", {"status": "interrupted", "phase": "analysis", "completed": completed,
                                                "error": type(exc).__name__+": "+str(exc)})
        raise
    write_json(directory/"progress.json", {"status": "complete", "completed": completed, "total": len(plan["runs"]),
                                            "elapsed_seconds": time.perf_counter()-started})
    print(f"READY: {directory/'REPORT.html'}", flush=True)
    return directory


def validate(config):
    def require(condition, message):
        if not condition:
            raise ValueError("Demographic validation failed: "+message)
    checks = []
    cfg = replace(config, steps=6, record_parentage=True, checkpoint_every=3)
    for mechanism in ("locus_mosaic", "chromosome_partition"):
        current = replace(cfg, multiparent_mechanism=mechanism, chromosome_lengths=(4, 4, 4, 4))
        full = advance(initialize(current))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"checkpoint.npz"
            partial = advance(initialize(current), until=3)
            save_checkpoint(path, partial)
            recovered = advance(load_checkpoint(path, current))
        require(state_digest(full) == state_digest(recovered), "exact state replay")
        require(full.metrics == recovered.metrics and full.parentage == recovered.parentage, "exact observations and lineage replay")
        require(full.ledger == recovered.ledger and full.resource_ledger == recovered.resource_ledger, "exact accounting replay")
        checks.append(f"{mechanism}: checkpoint/genome/identity/lineage/resource replay")
    extinct = advance(initialize(replace(cfg, survival_probability=0)))
    require(len(extinct.ids) == 0 and extinct.tick == 1, "extinction without restoration")
    checks.append("zero survival causes exact tick-1 extinction without replacement")
    print(json.dumps({"config": config.to_dict(), "checks": checks}, indent=2))
    return checks


def benchmark(config, sizes, steps, repeats, output):
    if not 1 <= repeats <= 5 or len(sizes) > 6:
        raise ValueError("Benchmark supports 1..5 repeats and up to six sizes")
    configurations = []
    active = [i for i, n in enumerate(config.initial_counts) if n]
    for capacity in sizes:
        census = max(len(active), int(.67*capacity))
        initial = [0]*len(STRATEGIES)
        for i in range(census):
            initial[active[i % len(active)]] += 1
        scale = capacity/config.capacity
        configurations.append(replace(config, capacity=capacity, initial_counts=tuple(initial), steps=steps,
                                      resource_capacity=config.resource_capacity*scale, initial_resources=config.initial_resources*scale,
                                      resource_renewal=config.resource_renewal*scale))
    if sum(c.capacity*c.steps*c.loci for c in configurations)*repeats > 10_000_000:
        raise ValueError("Benchmark workload too large")
    results = []
    for cfg in configurations:
        measurements = []
        for rep in range(repeats):
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                start = time.perf_counter()
                state = advance(initialize(replace(cfg, seed=cfg.seed+rep)))
                kernel = time.perf_counter()-start
                start = time.perf_counter()
                save_checkpoint(directory/"checkpoint.npz", state)
                checkpoint = time.perf_counter()-start
                start = time.perf_counter()
                write_outputs(directory, state, {"provenance": provenance()})
                io_seconds = time.perf_counter()-start
                measurements.append({"kernel_seconds": kernel, "checkpoint_seconds": checkpoint,
                                     "output_seconds": io_seconds, "total_seconds": kernel+checkpoint+io_seconds,
                                     "artifact_bytes": sum(p.stat().st_size for p in directory.iterdir()),
                                     "raw_newborns": sum(state.cumulative["raw_newborns"]), "terminal_population": len(state.ids)})
        tracemalloc.start()
        advance(initialize(cfg))
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        row = {"config": cfg.to_dict(), "measurements": measurements,
               "median_total_seconds": statistics.median(r["total_seconds"] for r in measurements),
               "median_kernel_seconds": statistics.median(r["kernel_seconds"] for r in measurements),
               "peak_traced_bytes_kernel": peak}
        results.append(row)
        print(f"demographic capacity={cfg.capacity}: {row['median_total_seconds']:.3f}s kernel+one checkpoint+CSV/gzip output", flush=True)
    report = {"provenance": provenance(), "scope": "Untraced timings include initialization, kernel, all logs, one final checkpoint and output. Peak traced kernel allocations measured separately; not process RSS. Long runs save additional checkpoints.", "results": results}
    write_json(output, report)
    return report
