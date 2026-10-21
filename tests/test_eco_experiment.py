from dataclasses import replace
import hashlib
import json
import subprocess
import sys

import numpy as np
import pytest

from evolution_lab_v2.eco_analysis import analyze, holm, sign_test, wilson
from evolution_lab_v2.eco_config import EcoConfig
from evolution_lab_v2.eco_experiment import plan_experiment, run_experiment
from evolution_lab_v2 import eco_experiment
from evolution_lab_v2.eco_io import simulate
from evolution_lab_v2.ecology import advance, initialize, state_digest


def specification():
    return {'name': 'test_comparison', 'master_seed': 2123, 'replicates': 2,
            'base': {'model': 'demographic', 'steps': 5, 'checkpoint_every': 2},
            'grid': {'multiparent_mechanism': ['locus_mosaic', 'chromosome_partition']}}


def test_exact_sign_test_and_holm_and_wilson():
    assert sign_test([1]*8)['p_two_sided'] == .0078125
    assert sign_test([1, -1, 0]) == {'positive': 1, 'negative': 1, 'ties': 1, 'p_two_sided': 1}
    assert sign_test([0]*8)['p_two_sided'] == 1
    np.testing.assert_allclose(holm([.01, .04, .03]), [.03, .06, .06])
    assert wilson(0, 0) is None
    low, high = wilson(0, 10)
    assert abs(low) < 1e-12 and abs(high-.2775328) < 1e-6


def test_plan_is_deterministic_paired_and_bounded():
    a, b = plan_experiment(specification()), plan_experiment(specification())
    assert a == b and len(a['runs']) == 4
    assert [r['config']['seed'] for r in a['runs'][:2]] == [r['config']['seed'] for r in a['runs'][2:]]
    assert a['upper_census_ticks'] == 4*336*5
    for data in [dict(specification(), replicates=0), dict(specification(), master_seed=-1),
                 dict(specification(), hidden='field'), dict(specification(), grid={'seed': [1]}),
                 dict(specification(), grid={'log_every': []}), dict(specification(), grid={'log_every': [1, 1]}),
                 dict(specification(), grid={'log_every': list(range(1, 258))})]:
        with pytest.raises(ValueError):
            plan_experiment(data)


def test_plan_only_creates_no_output(tmp_path):
    output = tmp_path/'not_created'
    summary = run_experiment(specification(), output, plan_only=True)
    assert summary['runs'] == 4 and not output.exists()


def test_end_to_end_plots_summaries_and_completed_resume(tmp_path):
    directory = tmp_path/'experiment'
    run_experiment(specification(), directory)
    manifest = json.loads((directory/'sweep_manifest.json').read_text())
    report = json.loads((directory/'analysis.json').read_text())
    assert manifest['status'] == 'complete'
    assert len(report['scenarios']) == 2
    assert len(report['scenarios'][0]['paired_contrasts']) == 6
    assert (directory/'REPORT.html').exists() and (directory/'REPORT.md').exists()
    assert (directory/'comparison.csv').exists() and (directory/'survival_curves.csv').exists()
    for name in report['figures']:
        assert (directory/name).read_bytes().startswith(b'\x89PNG')
        assert (directory/name.replace('.png', '.svg')).exists()
    first = directory/manifest['runs'][0]['path']
    digest = hashlib.sha256((first/'checkpoint.npz').read_bytes()).hexdigest()
    run_experiment(specification(), directory, resume=True)
    assert hashlib.sha256((first/'checkpoint.npz').read_bytes()).hexdigest() == digest
    changed = dict(specification(), master_seed=4)
    with pytest.raises(ValueError, match='identical plan'):
        run_experiment(changed, directory, resume=True)
    old = (first/'metrics.csv').read_bytes()
    (first/'metrics.csv').write_bytes(old+b'damaged')
    with pytest.raises(ValueError, match='hash mismatch'):
        analyze(directory, plots=False)
    (first/'metrics.csv').write_bytes(old)
    manifest['runs'] = manifest['runs'][1:]
    (directory/'sweep_manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Missing'):
        analyze(directory, plots=False)


def test_interrupted_batch_preserves_attempt_and_resumes_exactly(tmp_path, monkeypatch):
    data = specification()
    data['grid'] = {}
    data['replicates'] = 1
    directory = tmp_path/'interrupted'
    def pause(config, path, **kwargs):
        return simulate(config, path, stop_after=2, quiet=True)
    with monkeypatch.context() as context:
        context.setattr(eco_experiment, 'simulate', pause)
        with pytest.raises(ValueError, match='terminal'):
            run_experiment(data, directory)
    assert json.loads((directory/'progress.json').read_text())['status'] == 'interrupted'
    run_experiment(data, directory, resume=True)
    manifest = json.loads((directory/'sweep_manifest.json').read_text())
    run = manifest['runs'][0]
    cfg = EcoConfig.from_dict(run['config'])
    result = json.loads((directory/run['path']/'summary.json').read_text())
    assert result['state_sha256'] == state_digest(advance(initialize(cfg)))
    assert len(list(directory.glob('S000_R000_interrupted_*'))) == 1


def test_introduction_analysis_uses_actual_introductions_and_threshold(tmp_path):
    data = specification()
    data.update(experiment_kind='introduced_modifier', introduced_strategy='facultative', grid={})
    data['base'].update(initial_counts=[30, 0, 4, 0, 0, 0, 0], establishment_size=8)
    directory = tmp_path/'introduction'
    run_experiment(data, directory)
    report = json.loads((directory/'analysis.json').read_text())
    result = report['scenarios'][0]
    assert report['primary_endpoint'] == 'introduced_cohort_threshold_crossing_probability'
    assert result['introduced_modifier']['introductions'] == 2
    assert result['introduced_modifier']['introduced_count'] == 4
    assert not result['paired_contrasts']  # Unequal initial census is not a fair abundance contrast.


def test_all_scenarios_analyzed_while_only_plan_endpoints_are_plotted(tmp_path):
    data = specification()
    data.update(replicates=1, grid={'mating_cost': [0, .1, .2]})
    directory = tmp_path/'three_scenarios'
    run_experiment(data, directory)
    report = json.loads((directory/'analysis.json').read_text())
    assert [s['scenario'] for s in report['scenarios']] == ['S000', 'S001', 'S002']
    assert (directory/'trajectories_S000.png').exists()
    assert (directory/'trajectories_S002.png').exists()
    assert not (directory/'trajectories_S001.png').exists()


def test_eco_cli_validate_simulate_and_plan_only(tmp_path):
    config = tmp_path/'eco.json'
    config.write_text(json.dumps(EcoConfig(steps=3).to_dict()))
    for arguments in [['validate', '--config', config], ['simulate', '--config', config, '--output', tmp_path/'cli_run']]:
        result = subprocess.run([sys.executable, '-m', 'evolution_lab_v2', *map(str, arguments)], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(specification()))
    result = subprocess.run([sys.executable, '-m', 'evolution_lab_v2', 'experiment', '--config', str(spec), '--plan-only'], text=True, capture_output=True)
    assert result.returncode == 0 and '"runs": 4' in result.stdout
