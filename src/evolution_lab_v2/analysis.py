"""Pilot summaries only: independent replicates, scenario-specific bootstrap CIs."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .artifacts import provenance, write_json


def bootstrap_mean(values, seed=73021, draws=2000):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("Bootstrap values must be a nonempty finite vector")
    if len(values) < 2:
        return {"n": len(values), "mean": float(values.mean()), "ci95": None}
    rng = np.random.Generator(np.random.PCG64(seed))
    means = values[rng.integers(0, len(values), (draws, len(values)))].mean(axis=1)
    return {"n": len(values), "mean": float(values.mean()),
            "sd": float(values.std(ddof=1)), "ci95": np.quantile(means, [.025, .975]).tolist()}


def analyze(directory, output):
    directory = Path(directory)
    sweep = json.loads((directory / "sweep_manifest.json").read_text(encoding="utf-8"))
    if sweep["status"] != "complete" or not sweep["runs"]:
        raise ValueError("Incomplete or empty sweep")
    groups = defaultdict(list)
    paired = defaultdict(dict)
    observed = set()
    summary_hashes = {}
    paths = set()
    expected_seeds = set(sweep["replicate_seeds"])
    if not expected_seeds or len(expected_seeds) != len(sweep["replicate_seeds"]):
        raise ValueError("Invalid replicate seed plan")
    scenario_seeds = defaultdict(set)
    for run in sweep["runs"]:
        if run["path"] in paths:
            raise ValueError("Duplicate run path in sweep")
        paths.add(run["path"])
        summary_path = directory / run["path"] / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_hashes[run["path"]] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
        if not summary["complete"] or summary["config"] != run["config"]:
            raise ValueError("Incomplete or mismatched sweep run")
        cfg = dict(summary["config"])
        seed = cfg.pop("seed")
        key = json.dumps(cfg, sort_keys=True)
        if (key, seed) in observed:
            raise ValueError("Duplicate replicate in sweep")
        observed.add((key, seed))
        scenario_seeds[key].add(seed)
        value = summary["final"]["gene_diversity"]
        groups[key].append(value)
        reproduction = cfg.pop("reproduction")
        pairkey = json.dumps(cfg, sort_keys=True)
        paired[(pairkey, seed)][reproduction] = value
    if any(seeds != expected_seeds for seeds in scenario_seeds.values()):
        raise ValueError("Missing or unexpected replicate seeds")
    differences = defaultdict(list)
    for (cfg, _), values in paired.items():
        if set(values) == {"clone", "two_parent"}:
            differences[cfg].append(values["two_parent"] - values["clone"])
    report = {"endpoint": "final_gene_diversity", "bootstrap_seed": 73021, "bootstrap_draws": 2000,
              "provenance": provenance(), "summary_sha256": summary_hashes,
              "sweep_manifest_sha256": hashlib.sha256((directory / "sweep_manifest.json").read_bytes()).hexdigest(),
              "interpretation": "E1 drift diagnostic; no persistence or superiority inference. CIs are descriptive, unadjusted, and unstable for small n.",
              "scenarios": [{"config_without_seed": json.loads(k), **bootstrap_mean(v)} for k, v in groups.items()],
              "paired_two_minus_clone": [{"shared_config_without_seed": json.loads(k), **bootstrap_mean(v)} for k, v in differences.items()]}
    write_json(output, report)
    return report
