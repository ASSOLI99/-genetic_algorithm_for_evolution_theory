"""Catastrophe accounting, strategy-neutral hazards and exact recovery replay."""
from dataclasses import replace
import json

import numpy as np
import pytest

from evolution_lab_v2.eco_config import EcoConfig, STRATEGIES
from evolution_lab_v2 import ecology
from evolution_lab_v2.eco_io import load_checkpoint, save_checkpoint, simulate


def assert_balances(state):
    for row in state.ledger:
        assert row['end'] == (row['start']-row['survival_deaths']-row['catastrophe_deaths']
                              -row['maintenance_deaths']-row['capacity_adult_deaths']+row['realized_newborns'])
    for row in state.resource_ledger:
        assert abs(row['before']-row['catastrophe_loss']+row['renewal']-row['overflow']
                   -row['maintenance']-row['offspring']-row['after']) < 1e-7


@pytest.mark.parametrize('field,value', [
    ('catastrophe_probability', -0.1), ('catastrophe_probability', float('nan')),
    ('catastrophe_mortality', 1.01), ('catastrophe_resource_loss', True),
    ('catastrophe_renewal_factor', -1), ('catastrophe_duration', 0),
    ('catastrophe_duration', True), ('catastrophe_regime', 'earth_history'),
    ('catastrophe_regime', []),
])
def test_invalid_catastrophe_configuration(field, value):
    with pytest.raises(ValueError):
        EcoConfig(**{field: value})


def test_full_bottleneck_kills_all_before_reproduction_without_refill():
    cfg = EcoConfig(steps=5, catastrophe_regime='bottleneck', catastrophe_probability=1,
                    catastrophe_mortality=1, survival_probability=1, senescence_rate=0)
    state = ecology.advance(ecology.initialize(cfg))
    assert state.tick == 1 and len(state.ids) == 0
    assert sum(state.cumulative['catastrophe_deaths']) == sum(cfg.initial_counts)
    assert not state.parentage and set(state.extinct.values()) == {1}
    assert state.catastrophe_events[0]['deaths_by_strategy'] == list(cfg.initial_counts)
    assert_balances(state)


def test_zero_effect_shocks_leave_demographic_and_genetic_draws_unchanged():
    base = EcoConfig(steps=30)
    control = ecology.advance(ecology.initialize(base))
    shocks = ecology.advance(ecology.initialize(replace(base, catastrophe_regime='combined',
                 catastrophe_probability=1, catastrophe_mortality=0,
                 catastrophe_resource_loss=0, catastrophe_renewal_factor=1)))
    assert ecology.state_digest(control) == ecology.state_digest(shocks)
    for key in ('metrics', 'parentage', 'ledger', 'resource_ledger', 'cumulative'):
        assert getattr(control, key) == getattr(shocks, key)
    assert len(shocks.catastrophe_events) == base.steps


def test_exogenous_onsets_are_paired_despite_cost_and_demographic_changes():
    base = EcoConfig(steps=60, catastrophe_regime='combined', catastrophe_probability=.1,
                    catastrophe_mortality=.1, catastrophe_resource_loss=.1,
                    catastrophe_renewal_factor=.8)
    first = ecology.initialize(base)
    second = ecology.initialize(replace(base, mating_cost=.4, survival_probability=.7))
    np.testing.assert_array_equal(first.catastrophe_schedule, second.catastrophe_schedule)
    ecology.advance(first)
    ecology.advance(second)
    limit = min(first.tick, second.tick)
    assert [e['tick'] for e in first.catastrophe_events if e['tick'] <= limit] == [e['tick'] for e in second.catastrophe_events if e['tick'] <= limit]
    assert_balances(first)
    assert_balances(second)


def test_drought_duration_recovery_and_noncompounding_overlap():
    cfg = EcoConfig(steps=7, catastrophe_regime='drought', catastrophe_probability=0,
                    catastrophe_duration=3, catastrophe_resource_loss=0,
                    catastrophe_renewal_factor=.25, resource_renewal=100,
                    resource_capacity=10000, initial_resources=0, maintenance_cost=0,
                    fecundity=0, survival_probability=1, senescence_rate=0)
    single = ecology.initialize(cfg)
    single.catastrophe_schedule[0] = True
    ecology.advance(single)
    assert [r['renewal'] for r in single.resource_ledger] == [25, 25, 25, 100, 100, 100, 100]
    overlap = ecology.initialize(cfg)
    overlap.catastrophe_schedule[[0, 2]] = True
    ecology.advance(overlap)
    assert [r['renewal'] for r in overlap.resource_ledger] == [25, 25, 25, 25, 25, 100, 100]
    assert not sum(overlap.cumulative['catastrophe_deaths'])
    assert_balances(single)
    assert_balances(overlap)


def test_drought_stock_loss_and_starvation_are_separate_counters():
    cfg = EcoConfig(steps=1, catastrophe_regime='drought', catastrophe_probability=1,
                    catastrophe_resource_loss=1, resource_renewal=0,
                    survival_probability=1, senescence_rate=0, fecundity=0)
    state = ecology.advance(ecology.initialize(cfg))
    assert not len(state.ids)
    assert sum(state.cumulative['catastrophe_deaths']) == 0
    assert sum(state.cumulative['maintenance_deaths']) == sum(cfg.initial_counts)
    assert state.resource_ledger[0]['catastrophe_loss'] == cfg.initial_resources
    assert_balances(state)


def test_uniform_catastrophe_hazard_has_no_strategy_survival_bonus():
    totals = np.zeros(7)
    for seed in range(20):
        cfg = EcoConfig(seed=seed, steps=1, initial_counts=(200,)*7, capacity=1400,
                        catastrophe_regime='bottleneck', catastrophe_probability=1,
                        catastrophe_mortality=.5, survival_probability=1, fecundity=0,
                        senescence_rate=0, senescence_age=90, max_age=100, maintenance_cost=0)
        state = ecology.advance(ecology.initialize(cfg))
        totals += ecology.counts(state)
    # E[survivors per label]=100; tolerance is over five MC standard errors.
    np.testing.assert_allclose(totals/20, np.full(7, 100), atol=8)


@pytest.mark.parametrize('parentage', [False, True])
def test_resume_during_active_drought_is_exact(tmp_path, parentage):
    cfg = EcoConfig(seed=7, steps=30, catastrophe_regime='combined', catastrophe_probability=1,
                    catastrophe_mortality=.01, catastrophe_resource_loss=.02,
                    catastrophe_renewal_factor=.9, catastrophe_duration=4,
                    record_parentage=parentage, log_every=7)
    full = ecology.advance(ecology.initialize(cfg))
    partial = ecology.advance(ecology.initialize(cfg), until=11)
    assert partial.catastrophe_until > partial.tick
    checkpoint = tmp_path/'state.npz'
    save_checkpoint(checkpoint, partial)
    restored = ecology.advance(load_checkpoint(checkpoint, cfg))
    assert ecology.state_digest(full) == ecology.state_digest(restored)
    for key in ('catastrophe_until', 'catastrophe_events', 'metrics', 'parentage', 'ledger',
                'resource_ledger', 'events', 'cumulative'):
        assert getattr(full, key) == getattr(restored, key)
    for name in ecology.STREAMS:
        assert full.rngs[name].bit_generator.state == restored.rngs[name].bit_generator.state
    assert_balances(restored)


def test_catastrophe_logs_and_export_replay(tmp_path):
    cfg = EcoConfig(steps=12, catastrophe_regime='combined', catastrophe_probability=.5,
                    catastrophe_mortality=.1, catastrophe_resource_loss=.1,
                    catastrophe_renewal_factor=.8)
    complete = simulate(cfg, tmp_path/'full', quiet=True)
    simulate(cfg, tmp_path/'part', stop_after=5, quiet=True)
    recovered = simulate(cfg, tmp_path/'resumed', resume=tmp_path/'part/checkpoint.npz', quiet=True)
    assert complete['catastrophe_count'] > 0
    assert complete['catastrophe_count'] == recovered['catastrophe_count']
    assert 'catastrophes.csv' in complete['manifest']['artifact_sha256']
    for filename in ('catastrophes.csv', 'resources.csv', 'ledger.csv', 'events.csv', 'metrics.csv', 'parentage.csv.gz'):
        assert (tmp_path/'full'/filename).read_bytes() == (tmp_path/'resumed'/filename).read_bytes()


def test_checkpoint_rejects_invalid_recovery_and_old_schema(tmp_path):
    cfg = EcoConfig(steps=5)
    path = tmp_path/'state.npz'
    save_checkpoint(path, ecology.initialize(cfg))
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    meta = json.loads(str(arrays['metadata'].item()))
    meta['catastrophe_until'] = -1
    arrays['metadata'] = np.array(json.dumps(meta))
    np.savez_compressed(path, **arrays)
    with pytest.raises(ValueError, match='recovery clock'):
        load_checkpoint(path, cfg)
    meta['schema'] = 'demographic-1'
    arrays.pop('catastrophe_schedule')
    arrays['metadata'] = np.array(json.dumps(meta))
    np.savez_compressed(path, **arrays)
    with pytest.raises(ValueError, match='signature mismatch'):
        load_checkpoint(path, cfg)
