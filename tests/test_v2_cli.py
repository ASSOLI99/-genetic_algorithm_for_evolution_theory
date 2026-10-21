import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from evolution_lab_v2.analysis import analyze, bootstrap_mean
from evolution_lab_v2.cli import main


def invoke(*args):
    return subprocess.run([sys.executable, '-m', 'evolution_lab_v2', *map(str, args)],
                          capture_output=True, text=True)


def test_cli_validate():
    result = invoke('validate')
    assert result.returncode == 0, result.stderr
    assert 'checkpoint replay' in result.stdout


def test_cli_simulate_checkpoint_resume_and_artifacts(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'population_size': 20, 'generations': 5,
                                 'reproduction': 'two_parent', 'log_every': 2}))
    full, part, resumed = [tmp_path / name for name in ('full', 'part', 'resumed')]
    for args in [('--output', full), ('--output', part, '--stop-after', 3),
                 ('--output', resumed, '--resume', part / 'checkpoint.npz')]:
        result = invoke('simulate', '--config', config, *args)
        assert result.returncode == 0, result.stderr
    a, b = [json.loads((p/'summary.json').read_text()) for p in (full, resumed)]
    assert a['genome_sha256'] == b['genome_sha256']
    assert (full/'metrics.csv').read_bytes() == (resumed/'metrics.csv').read_bytes()
    assert (full/'parentage.csv').read_bytes() == (resumed/'parentage.csv').read_bytes()
    with (full/'parentage.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20 * 5
    assert all(r['parent_0'] != r['parent_1'] for r in rows)
    assert not json.loads((part/'summary.json').read_text())['complete']
    assert a['manifest']['provenance']['git_sha']
    assert len(a['manifest']['artifact_sha256']) == 3
    result = invoke('simulate', '--config', config, '--output', full)
    assert result.returncode == 2


def test_cli_invalid_config_fails_without_output(tmp_path):
    cfg = tmp_path/'config.json'
    cfg.write_text('{"population_size": 1000000}')
    output = tmp_path/'invalid'
    result = invoke('simulate', '--config', cfg, '--output', output)
    assert result.returncode == 2 and not output.exists()


def test_small_preregistered_sweep_and_analysis(tmp_path):
    cfg, grid = tmp_path/'config.json', tmp_path/'grid.json'
    cfg.write_text('{"population_size": 12, "generations": 2}')
    grid.write_text('{"reproduction": ["clone", "two_parent"]}')
    directory = tmp_path/'sweep'
    result = invoke('sweep', '--config', cfg, '--grid', grid, '--output', directory, '--replicates', 3)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((directory/'sweep_manifest.json').read_text())
    analysis = json.loads((directory/'analysis.json').read_text())
    assert manifest['status'] == 'complete'
    assert len(manifest['runs']) == 6
    assert len(analysis['scenarios']) == 2
    assert analysis['paired_two_minus_clone'][0]['n'] == 3
    seeds = [r['config']['seed'] for r in manifest['runs']]
    assert seeds[:3] == seeds[3:]
    first_summary = directory/manifest['runs'][0]['path']/'summary.json'
    summary = json.loads(first_summary.read_text())
    summary['complete'] = False
    first_summary.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='Incomplete'):
        analyze(directory, tmp_path/'bad.json')
    summary['complete'] = True
    first_summary.write_text(json.dumps(summary))
    manifest['runs'].append(manifest['runs'][0])
    (directory/'sweep_manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Duplicate'):
        analyze(directory, tmp_path/'duplicate.json')
    manifest['runs'] = manifest['runs'][1:-1]
    (directory/'sweep_manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Missing'):
        analyze(directory, tmp_path/'missing.json')


def test_bootstrap_reproducibility_and_insufficient_n():
    assert bootstrap_mean([1, 2, 4]) == bootstrap_mean([1, 2, 4])
    assert bootstrap_mean([1])['ci95'] is None
    with pytest.raises(ValueError):
        bootstrap_mean([])


def test_benchmark_emits_measured_scope(tmp_path):
    output = tmp_path/'benchmark.json'
    assert main(['benchmark', '--sizes', '10,20', '--generations', '2',
                 '--repeats', '1', '--output', str(output)]) == 0
    results = json.loads(output.read_text())['results']
    assert len(results) == 4
    assert all(r['median_seconds'] > 0 and r['peak_traced_bytes'] > 0 for r in results)
