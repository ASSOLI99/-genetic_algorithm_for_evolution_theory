"""Atomic ecological checkpoints, complete ledgers, deterministic compressed lineage."""
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

from .artifacts import provenance, signature, write_json
from .eco_config import EcoConfig, STRATEGIES
from .ecology import ARRAYS, STREAMS, EcoState, advance, initialize, observe, state_digest


def save_checkpoint(path, state):
    path = Path(path)
    meta = {"schema": "demographic-2", "signature": signature(), "config": state.config.to_dict(),
            "tick": state.tick, "resources": state.resources, "next_id": state.next_id,
            "catastrophe_until": state.catastrophe_until,
            "rng_states": {name: rng.bit_generator.state for name, rng in state.rngs.items()}}
    for key in ("founders", "metrics", "ledger", "resource_ledger", "parentage", "events", "extinct", "established", "cumulative", "catastrophe_events"):
        meta[key] = getattr(state, key)
    arrays = {name: getattr(state, name) for name in (*ARRAYS, "environment", "parasite", "catastrophe_schedule")}
    temporary = path.with_name(path.name+".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays, metadata=np.array(json.dumps(meta, allow_nan=False)))
    temporary.replace(path)


def load_checkpoint(path, config):
    with np.load(path, allow_pickle=False) as archive:
        meta = json.loads(str(archive["metadata"].item()))
        if meta["schema"] != "demographic-2" or meta["signature"] != signature():
            raise ValueError("Demographic checkpoint code/runtime signature mismatch")
        arrays = {name: archive[name].copy() for name in (*ARRAYS, "environment", "parasite", "catastrophe_schedule")}
    if EcoConfig.from_dict(meta["config"]) != config:
        raise ValueError("Demographic checkpoint configuration mismatch")
    tick, next_id = meta["tick"], meta["next_id"]
    if type(tick) is not int or not 0 <= tick <= config.steps or type(next_id) is not int or next_id < sum(config.initial_counts):
        raise ValueError("Invalid demographic checkpoint clock/identity counter")
    n = len(arrays["ids"])
    if n > config.capacity:
        raise ValueError("Checkpoint census exceeds capacity")
    for name in ARRAYS:
        expected = (n, 2, config.loci) if name == "genomes" else (n,)
        if arrays[name].shape != expected:
            raise ValueError(f"Invalid demographic checkpoint {name} shape")
    for name in ("genomes", "environment", "parasite"):
        if arrays[name].dtype != np.uint8 or (arrays[name] > 1).any():
            raise ValueError(f"Invalid binary {name}")
    if arrays["environment"].shape != (config.steps+1, config.loci) or arrays["parasite"].shape != (max(1, config.loci//4),):
        raise ValueError("Invalid environmental checkpoint shape")
    if arrays["catastrophe_schedule"].shape != (config.steps,) or arrays["catastrophe_schedule"].dtype != np.bool_:
        raise ValueError("Invalid catastrophe schedule")
    until = meta["catastrophe_until"]
    if type(until) is not int or not 0 <= until <= config.steps+config.catastrophe_duration:
        raise ValueError("Invalid catastrophe recovery clock")
    if config.catastrophe_regime == "none" and (arrays["catastrophe_schedule"].any() or until):
        raise ValueError("Inactive catastrophes have active state")
    for name in ("ids", "strategy", "birth_tick", "mating_type"):
        if arrays[name].dtype.kind != "i":
            raise ValueError("Identity/state arrays must be signed integers")
    if len(np.unique(arrays["ids"])) != n or (arrays["ids"] < 0).any() or (arrays["ids"] >= next_id).any():
        raise ValueError("Invalid persistent identities")
    if (arrays["strategy"] < 0).any() or (arrays["strategy"] >= len(STRATEGIES)).any():
        raise ValueError("Invalid strategy labels")
    if (arrays["mating_type"] < 0).any() or (arrays["mating_type"] >= len(config.compatibility_matrix)).any():
        raise ValueError("Invalid mating types")
    if (arrays["birth_tick"] > tick).any():
        raise ValueError("Future-born individual in checkpoint")
    if not np.isfinite(arrays["mix_probability"]).all() or ((arrays["mix_probability"] < 0) | (arrays["mix_probability"] > 1)).any():
        raise ValueError("Invalid modifier trait")
    if not math.isfinite(meta["resources"]) or not 0 <= meta["resources"] <= config.resource_capacity:
        raise ValueError("Invalid resource stock")
    if len(meta["ledger"]) != tick*len(STRATEGIES) or len(meta["resource_ledger"]) != tick:
        raise ValueError("Incomplete accounting history")
    if config.record_parentage and len(meta["parentage"]) != next_id-sum(config.initial_counts):
        raise ValueError("Incomplete parentage history")
    rngs = {}
    for name in STREAMS:
        rngs[name] = np.random.Generator(np.random.PCG64())
        rngs[name].bit_generator.state = meta["rng_states"][name]
    state = EcoState(config=config, tick=tick, resources=meta["resources"], next_id=next_id, rngs=rngs,
                     catastrophe_until=until, **arrays)
    for key in ("founders", "metrics", "ledger", "resource_ledger", "parentage", "events", "extinct", "established", "cumulative", "catastrophe_events"):
        setattr(state, key, meta[key])
    return state


def write_csv(path, rows, fieldnames=None):
    path = Path(path)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    def write(stream):
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, separators=(",", ":")) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    if path.suffix == ".gz":
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
                    write(stream)
    else:
        with path.open("w", encoding="utf-8", newline="") as stream:
            write(stream)


def write_outputs(directory, state, manifest):
    directory = Path(directory)
    metrics = list(state.metrics)
    if metrics[-1]["tick"] != state.tick:
        metrics.extend(observe(state))
    write_csv(directory/"metrics.csv", metrics)
    write_csv(directory/"ledger.csv", state.ledger, ["tick", "strategy", "start", "end", *state.cumulative])
    write_csv(directory/"resources.csv", state.resource_ledger,
              ["tick", "before", "renewal", "catastrophe_loss", "renewal_multiplier", "overflow", "maintenance", "offspring", "after"])
    write_csv(directory/"catastrophes.csv", state.catastrophe_events,
              ["tick", "regime", "population_before", "deaths", "counts_before", "deaths_by_strategy",
               "stock_before", "stock_lost", "stock_after_shock", "renewal_depressed_until_exclusive"])
    write_csv(directory/"founders.csv", state.founders)
    write_csv(directory/"events.csv", state.events, ["tick", "event", "strategy", "threshold"])
    write_csv(directory/"parentage.csv.gz", state.parentage,
              ["offspring_id", "birth_tick", "mating_tick", "strategy", "parents", "parent_birth_ticks", "parent_strategies",
               "parent_mating_types", "contributed_copies", "requested_parents", "fallback", "funded", "recruited"])
    final = observe(state)
    by_strategy = {}
    for i, row in enumerate(final):
        by_strategy[row["strategy"]] = {**row, "initial_count": state.config.initial_counts[i],
                                       "extinction_tick": state.extinct.get(row["strategy"]),
                                       "threshold_tick": state.established.get(row["strategy"]),
                                       "fixation_tick": next((e['tick'] for e in state.events if e['event'] == 'strategy_fixation' and e['strategy'] == row['strategy']), None),
                                       "realized_births_per_offspring_resource": state.cumulative['realized_newborns'][i]/state.cumulative['offspring_resources'][i] if state.cumulative['offspring_resources'][i] else None,
                                       "cumulative": {k: v[i] for k, v in state.cumulative.items()}}
    complete = state.tick == state.config.steps or len(state.ids) == 0
    manifest["status"] = "complete" if complete else "paused"
    manifest["artifact_sha256"] = {name: hashlib.sha256((directory/name).read_bytes()).hexdigest()
                                    for name in ("metrics.csv", "ledger.csv", "resources.csv", "catastrophes.csv", "founders.csv", "events.csv", "parentage.csv.gz", "checkpoint.npz")}
    summary = {"schema_version": 1, "model": "demographic", "config": state.config.to_dict(),
               "tick": state.tick, "horizon": state.config.steps, "complete": complete,
               "total_population": len(state.ids), "resources": state.resources,
               "state_sha256": state_digest(state),
               "environment_sha256": hashlib.sha256(state.environment.tobytes()).hexdigest(),
               "catastrophe_count": len(state.catastrophe_events),
               "catastrophe_schedule_sha256": hashlib.sha256(state.catastrophe_schedule.tobytes()).hexdigest(),
               "strategies": by_strategy, "manifest": manifest}
    write_json(directory/"manifest.json", manifest)
    write_json(directory/"summary.json", summary)
    return summary


def simulate(config, directory, resume=None, stop_after=None, quiet=False):
    state = load_checkpoint(resume, config) if resume else initialize(config)
    if stop_after is not None and not state.tick <= stop_after <= config.steps:
        raise ValueError("Invalid stop-after tick")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "model": "demographic", "config": config.to_dict(),
                "provenance": provenance(), "status": "running", "protocol": "ECO_PROTOCOL.md"}
    manifest["extension_protocol"] = "DISTURBANCE_PROTOCOL.md"
    if resume:
        manifest["resume"] = {"path": str(Path(resume).resolve()), "sha256": hashlib.sha256(Path(resume).read_bytes()).hexdigest()}
    write_json(directory/"manifest.json", manifest)
    def checkpoint(current):
        save_checkpoint(directory/"checkpoint.npz", current)
        if not quiet:
            print(f"{directory.name}: tick {current.tick}/{config.steps}; population={len(current.ids)}", flush=True)
    advance(state, until=stop_after, checkpoint=checkpoint)
    return write_outputs(directory, state, manifest)
