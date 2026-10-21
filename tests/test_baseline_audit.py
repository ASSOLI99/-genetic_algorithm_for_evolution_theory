"""Characterize the unchanged baseline, including known defects."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from evolution_lab_verified import NAMES, choose_distinct_parents, simulate

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_bytes_unchanged():
    expected = json.loads((ROOT / "baseline_sha256.json").read_text())
    # Historical results are optional local data; protected source is required.
    for name, digest in expected.items():
        path = ROOT / name
        if name == "results_10k.csv" and not path.exists():
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("mode,seed", [("invasion", 2026), ("established", 102026)])
def test_baseline_determinism_and_population_conservation(mode, seed):
    first = simulate(seed=seed, generations=200, capacity=10000, mode=mode)
    assert first == simulate(seed=seed, generations=200, capacity=10000, mode=mode)
    assert all(sum(r[k] for k in NAMES) == r["total"] for r in first)


@pytest.mark.parametrize("mode,seed", [("invasion", 2026), ("established", 102026)])
def test_baseline_matches_optional_historical_csv_prefix(mode, seed):
    if not (ROOT / "results_10k.csv").exists():
        pytest.skip("Historical results are local-only; source and determinism checks run separately")
    first = simulate(seed=seed, generations=200, capacity=10000, mode=mode)
    with (ROOT / "results_10k.csv").open(newline="") as f:
        expected = [r for r in csv.DictReader(f) if r["mode"] == mode and int(r["seed"]) == seed][:3]
    assert [{k: str(v) for k, v in r.items()} for r in first] == expected


def test_known_uint8_initial_allocation_bias():
    rec = simulate(seed=102026, generations=0, capacity=10000)[0]
    assert [rec[k] for k in NAMES] == [1176, 1176, 1176, 1176, 1148, 1148]
    correct = np.bincount(np.arange(7000, dtype=np.int64) % 6)
    assert correct.max() - correct.min() == 1


def test_known_zero_birth_shape_defect():
    assert choose_distinct_parents(np.random.default_rng(1), np.arange(8), np.ones(8)/8, 0, 8).shape == (0,)


def test_known_skewed_sampling_failure():
    weights = np.full(50, .001/49)
    weights[0] = .999
    with pytest.raises(RuntimeError, match="distinct mates"):
        choose_distinct_parents(np.random.default_rng(1), np.arange(50), weights, 3, 8)


def test_known_invalid_mutation_probability_accepted():
    assert simulate(generations=1, capacity=120, mutation_rate=-.1)


@pytest.mark.parametrize("setting", ["environmental_change", "log_every"])
def test_known_zero_interval_failure(setting):
    with pytest.raises(ZeroDivisionError):
        simulate(generations=1, capacity=120, **{setting: 0})
