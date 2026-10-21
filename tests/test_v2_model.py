from dataclasses import replace
import json

import numpy as np
import pytest

from evolution_lab_v2.artifacts import load_checkpoint, save_checkpoint
from evolution_lab_v2.config import Config
from evolution_lab_v2.model import advance, initialize, observe, step


@pytest.mark.parametrize("change", [dict(seed=-1), dict(seed=True), dict(population_size=0),
    dict(generations=1.2), dict(mutation_rate=-.1), dict(mutation_rate=float('nan')),
    dict(recombination_rate=.6), dict(selection_coefficient=1), dict(chromosome_lengths=[]),
    dict(chromosome_lengths=[0]), dict(reproduction='eight_parent'), dict(log_every=0),
    dict(population_size=10001), dict(population_size=1000, generations=10000),
    dict(reproduction='two_parent', population_size=1)])
def test_config_rejects_invalid_and_large_work(change):
    with pytest.raises(ValueError):
        Config(**change)


def test_config_roundtrip_and_unknown_fields():
    cfg = Config()
    assert Config.from_dict(json.loads(json.dumps(cfg.to_dict()))) == cfg
    with pytest.raises(ValueError):
        Config.from_dict({"hidden_cost": .1})


@pytest.mark.parametrize("mode", ['clone', 'two_parent'])
@pytest.mark.parametrize("split", [0, 3, 10])
def test_exact_checkpoint_replay_and_all_parentage(tmp_path, mode, split):
    cfg = Config(reproduction=mode, population_size=30, generations=10,
                 chromosome_lengths=(3, 4), mutation_rate=.01, log_every=4)
    full = advance(initialize(cfg))
    partial = advance(initialize(cfg), until=split)
    path = tmp_path / "checkpoint.npz"
    save_checkpoint(path, partial)
    resumed = advance(load_checkpoint(path, cfg))
    np.testing.assert_array_equal(full.genomes, resumed.genomes)
    np.testing.assert_array_equal(full.parentage, resumed.parentage)
    assert full.rng.bit_generator.state == resumed.rng.bit_generator.state
    assert full.records == resumed.records
    assert len(full.parentage) == cfg.generations
    assert len(full.genomes) == cfg.population_size
    if mode == 'two_parent':
        assert all((groups[:, 0] != groups[:, 1]).all() for groups in full.parentage)


def test_checkpoint_mismatch_rejected(tmp_path):
    cfg = Config(generations=2)
    path = tmp_path / 'checkpoint.npz'
    save_checkpoint(path, initialize(cfg))
    with pytest.raises(ValueError, match='configuration mismatch'):
        load_checkpoint(path, replace(cfg, mutation_rate=.1))


@pytest.mark.parametrize('damage', ['genomes', 'signature', 'records', 'parentage'])
def test_damaged_checkpoints_rejected(tmp_path, damage):
    cfg = Config(reproduction='two_parent', generations=2, population_size=10)
    path = tmp_path/'checkpoint.npz'
    save_checkpoint(path, advance(initialize(cfg), until=1))
    with np.load(path, allow_pickle=False) as archive:
        data = {k: archive[k].copy() for k in archive.files}
    if damage == 'genomes':
        data['genomes'][0, 0, 0] = 2
    elif damage == 'parentage':
        data['parentage'][0, 0] = [0, 0]
    else:
        metadata = json.loads(str(data['metadata'].item()))
        if damage == 'signature':
            metadata['signature']['package'] = 'incompatible'
        else:
            metadata['records'] = []
        data['metadata'] = np.array(json.dumps(metadata))
    np.savez_compressed(path, **data)
    with pytest.raises(ValueError):
        load_checkpoint(path, cfg)


@pytest.mark.parametrize('mode', ['clone', 'two_parent'])
def test_monomorphic_no_mutation_and_symmetric_mutation(mode):
    cfg = Config(reproduction=mode, population_size=20, generations=2, initial_frequency=0)
    assert not advance(initialize(cfg)).genomes.any()
    state = initialize(replace(cfg, mutation_rate=1))
    step(state)
    assert (state.genomes == 1).all()
    step(state)
    assert not state.genomes.any()


def test_clone_inherits_both_homologs_exactly():
    state = initialize(Config(generations=1))
    founders = state.genomes.copy()
    step(state)
    np.testing.assert_array_equal(state.genomes, founders[state.parentage[0][:, 0]])


def test_two_parent_transmission_at_homozygous_diagnostic_loci():
    state = initialize(Config(reproduction='two_parent', population_size=2, generations=1))
    state.genomes[0] = 0
    state.genomes[1] = 1
    step(state)
    assert (state.genomes.sum(axis=1) == 1).all()


@pytest.mark.parametrize('mode', ['clone', 'two_parent'])
def test_neutral_mean_and_drift_against_exact_one_step_theory(mode):
    # Fixed founders: half 0/0, half 1/1. Distinct-parent sampling excludes selfing.
    n, replicates = 40, 1200
    values = []
    cfg = Config(reproduction=mode, population_size=n, generations=1, chromosome_lengths=(1,))
    for seed in range(replicates):
        state = initialize(replace(cfg, seed=seed))
        state.genomes[:n//2] = 0
        state.genomes[n//2:] = 1
        step(state)
        values.append(float(state.genomes.mean()))
    expected_variance = .25/n if mode == 'clone' else (.25 - .25/(n-1))/(2*n)
    # Six MC standard errors for mean; broad variance gate avoids flaky significance tests.
    assert abs(np.mean(values)-.5) < 6 * np.sqrt(expected_variance/replicates)
    assert abs(np.var(values, ddof=1)/expected_variance - 1) < .20


def test_neutral_founders_and_metrics_symmetric():
    clone = initialize(Config())
    two = initialize(Config(reproduction='two_parent'))
    np.testing.assert_array_equal(clone.genomes, two.genomes)
    assert observe(clone) == observe(two)


def test_observation_does_not_consume_randomness():
    state = initialize(Config())
    before = dict(state.rng.bit_generator.state)
    observe(state)
    assert state.rng.bit_generator.state == before
