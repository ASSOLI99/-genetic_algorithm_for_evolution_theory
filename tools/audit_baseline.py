"""Read-only source verification; optional local historical CSV replay."""
import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evolution_lab_verified import NAMES, simulate  # noqa: E402


def audit(full=False):
    started = time.perf_counter()
    expected_hashes = json.loads((ROOT / "baseline_sha256.json").read_text())
    csv_path = ROOT / "results_10k.csv"
    hashes = {}
    for name, digest in expected_hashes.items():
        path = ROOT / name
        if name == "results_10k.csv" and not path.exists():
            continue
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[name] != digest:
            raise ValueError(f"Baseline bytes changed: {name}")
    if not csv_path.exists():
        if full:
            raise FileNotFoundError("--full requires the optional local results_10k.csv")
        print("PASS protected baseline source hashes; historical CSV is not included", flush=True)
        return {"python": platform.python_version(), "numpy": np.__version__,
                "sha256": hashes, "csv_available": False, "csv_rows": 0, "runs": [],
                "verification_scope": "source_integrity_only",
                "seconds": time.perf_counter() - started}
    with (ROOT / "results_10k.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    assert columns == ["seed", "mode", "generation", "total", "mean_fitness",
                       "allelic_diversity", "mixed_age_matings", *NAMES]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["mode"], int(r["seed"]))].append(r)
        assert sum(int(r[k]) for k in NAMES) == int(r["total"])
        assert all(int(r[k]) >= 0 for k in NAMES)
        assert 0 <= float(r["mean_fitness"]) <= 1
        assert 0 <= float(r["allelic_diversity"]) <= .5
    assert set(groups) == {(m, 2026 + 137 * i + offset)
                           for m, offset in [("invasion", 0), ("established", 100000)]
                           for i in range(5)}
    runs = []
    for (mode, seed), series in groups.items():
        assert [int(r["generation"]) for r in series] == list(range(0, 10001, 100))
        assert all(int(b["mixed_age_matings"]) >= int(a["mixed_age_matings"])
                   for a, b in zip(series, series[1:]))
        end = 10000 if full else 200
        actual = simulate(seed=seed, generations=end, capacity=10000, mode=mode)
        target = series if full else series[:3]
        assert len(actual) == len(target)
        differences = [(r["generation"], k, str(v), e[k])
                       for r, e in zip(actual, target) for k, v in r.items() if str(v) != e[k]]
        assert not differences, differences[:5]
        run = {"mode": mode, "seed": seed, "csv_rows": len(series), "replayed_through": end,
               "exact_match": True, "initial_counts": {k: int(series[0][k]) for k in NAMES},
               "final_counts": {k: int(series[-1][k]) for k in NAMES}}
        runs.append(run)
        print(f"PASS {mode} seed={seed} replayed through {end}", flush=True)
    return {"python": platform.python_version(), "numpy": np.__version__, "sha256": hashes,
            "csv_available": True, "verification_scope": "source_integrity_and_historical_replay",
            "csv_rows": len(rows), "columns": columns, "runs": runs,
            "baseline_parameters": {"capacity": 10000, "generations": 10000,
                                    "sex_cost": .12, "partner_cost": .08, "mutation_rate": .001,
                                    "environmental_change": 150, "parasite_strength": .23,
                                    "log_every": 100},
            "seconds": time.perf_counter() - started}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/baseline_audit.json")
    args = parser.parse_args()
    report = audit(args.full)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS {report['csv_rows']} CSV rows; report: {args.output}")
