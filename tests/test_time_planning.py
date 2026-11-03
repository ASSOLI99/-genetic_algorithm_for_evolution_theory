"""Deep-time arithmetic cannot silently launch or authorize a huge simulation."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from evolution_lab_v2.artifacts import signature
from evolution_lab_v2.eco_config import EcoConfig
from evolution_lab_v2.planning import plan_time


def test_hundred_million_years_is_only_a_guarded_workload_plan(monkeypatch):
    from evolution_lab_v2 import ecology
    def forbidden(*args, **kwargs):
        raise AssertionError('Planning launched a simulation')
    monkeypatch.setattr(ecology, 'initialize', forbidden)
    result = plan_time(EcoConfig(), 100_000_000, 1, replicates=8)
    assert result['simulation_launched'] is False
    assert result['steps_per_run'] == 100_000_000
    assert result['upper_census_ticks_per_run'] == 33_600_000_000
    assert result['upper_locus_ticks_all_runs'] == 4_300_800_000_000
    assert result['preallocated_environment_bytes_per_run'] == 1_600_000_016
    assert result['retained_accounting_rows_per_run'] == 800_000_000
    assert not result['within_current_workload_guards']
    assert result['naive_kernel_extrapolation_seconds_per_run'] is None
    assert 'not empirical calibration' in result['calendar_mapping']


def test_calendar_rounding_and_small_plan():
    result = plan_time(EcoConfig(), 10, .3)
    assert result['steps_per_run'] == 34
    assert result['rounded_calendar_years'] >= 10
    assert result['within_current_workload_guards']


@pytest.mark.parametrize('years,unit,reps', [(0, 1, 1), (1, 0, 1),
    (float('inf'), 1, 1), (1, float('nan'), 1), (True, 1, 1), (1, 1, 0), (1, 1, True)])
def test_invalid_calendar_inputs(years, unit, reps):
    with pytest.raises(ValueError):
        plan_time(EcoConfig(), years, unit, reps)


def test_estimate_requires_matching_complete_benchmark(tmp_path):
    cfg = EcoConfig(steps=100, record_parentage=False)
    path = tmp_path/'benchmark.json'
    measured = {'provenance': signature(), 'results': [{'config': cfg.to_dict(),
                'measurements': [{'terminal_tick': 100, 'kernel_seconds': 1.0}]}]}
    path.write_text(json.dumps(measured))
    result = plan_time(cfg, 10000, 1, benchmark=path)
    assert result['naive_kernel_extrapolation_seconds_per_run'] == [100, 100]
    assert not result['within_current_workload_guards']
    measured['results'][0]['measurements'][0]['terminal_tick'] = 5
    path.write_text(json.dumps(measured))
    assert plan_time(cfg, 10000, 1, benchmark=path)['naive_kernel_extrapolation_seconds_per_run'] is None
    measured['provenance']['package'] = 'different-source'
    path.write_text(json.dumps(measured))
    result = plan_time(cfg, 10000, 1, benchmark=path)
    assert result['naive_kernel_extrapolation_seconds_per_run'] is None
    assert result['benchmark_rejections']


def test_cli_planning_creates_no_run(tmp_path):
    config = tmp_path/'config.json'
    config.write_text(json.dumps(EcoConfig().to_dict()))
    output = tmp_path/'plan.json'
    result = subprocess.run([sys.executable, '-m', 'evolution_lab_v2', 'plan-time',
                             '--config', str(config), '--years', '100000000',
                             '--years-per-step', '1', '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())['simulation_launched'] is False
    assert set(p.name for p in tmp_path.iterdir()) == {'config.json', 'plan.json'}
