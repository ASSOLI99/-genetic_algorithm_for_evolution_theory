"""Demographic invariants, eligibility, shared budgets and hypothetical inheritance."""
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from evolution_lab_v2.eco_config import EcoConfig, STRATEGIES
from evolution_lab_v2.eco_genetics import anchored_uniform_groups, compatible_groups, inherit
from evolution_lab_v2 import ecology


@given(n=st.integers(8, 90), k=st.sampled_from([1, 2, 4, 8]), b=st.integers(0, 40))
@settings(max_examples=80, derandomize=True)
def test_fast_anchored_sampler(n, k, b):
    rng = np.random.default_rng(30)
    pool = np.arange(n)*3+17
    first = rng.choice(pool, b)
    groups = anchored_uniform_groups(rng, pool, first, k)
    assert groups.shape == (b, k)
    np.testing.assert_array_equal(groups[:, 0], first)
    assert np.isin(groups, pool).all()
    assert all(len(set(row)) == k for row in groups)


def test_anchored_uniformity_and_insufficient_pool():
    groups = anchored_uniform_groups(np.random.default_rng(11), np.arange(5), np.full(30000, 2), 4)
    for col in range(1, 4):
        freq = np.bincount(groups[:, col], minlength=5)/len(groups)
        np.testing.assert_allclose(freq[[0, 1, 3, 4]], .25, atol=.015)
    with pytest.raises(ValueError):
        anchored_uniform_groups(np.random.default_rng(1), np.arange(3), [0], 4)


def test_mating_types_are_not_parent_count():
    rng = np.random.default_rng(2)
    groups = compatible_groups(rng, np.arange(12), np.array([0, 1, 2]), 8, np.zeros(12, dtype=int), ((True,),))
    assert (groups >= 0).all()  # One type permits eight distinct contributors.
    types = np.arange(12) % 2
    matrix = np.array([[False, True], [True, False]])
    pairs = compatible_groups(rng, np.arange(12), np.array([0, 1, 2]), 2, types, matrix)
    assert all(types[row[0]] != types[row[1]] for row in pairs)
    groups = compatible_groups(rng, np.arange(12), np.array([0]), 4, types, matrix)
    assert (groups == -1).all()  # Pairwise incompatibility, not "four types required".


@pytest.mark.parametrize('mechanism', ['locus_mosaic', 'chromosome_partition'])
@pytest.mark.parametrize('k', [1, 2, 4, 8])
def test_genetic_contribution_and_ploidy(mechanism, k):
    rng = np.random.default_rng(14)
    genomes = rng.integers(0, 2, (20, 2, 16), dtype=np.uint8)
    groups = anchored_uniform_groups(rng, np.arange(20), np.arange(20), k)
    children, contributions = inherit(rng, genomes, groups, (4, 4, 4, 4), .05, mechanism)
    assert children.shape == (20, 2, 16) and children.dtype == np.uint8
    assert ((children == 0) | (children == 1)).all()
    assert (contributions.sum(axis=1) == 32).all()
    assert (contributions > 0).all()
    if mechanism == 'chromosome_partition' or k <= 2:
        assert (contributions == 32//k).all()
    if k == 1:
        np.testing.assert_array_equal(children, genomes)


def test_partition_transmits_intact_gamete_chromosomes():
    # Each parent has a unique chromosome-coded binary signature; r=0.
    genomes = np.zeros((8, 2, 16), dtype=np.uint8)
    for parent in range(8):
        genomes[parent] = [(parent >> (locus % 3)) & 1 for locus in range(16)]
    groups = np.tile(np.arange(8), (40, 1))
    children, contributions = inherit(np.random.default_rng(11), genomes, groups, (4, 4, 4, 4), 0, 'chromosome_partition')
    assert (contributions == 4).all()
    for child in children:
        for homolog in child:
            for start in range(0, 16, 4):
                assert any(np.array_equal(homolog[start:start+4], g[0, start:start+4]) for g in genomes)


@pytest.mark.parametrize('k', [4, 8])
@pytest.mark.parametrize('mechanism', ['locus_mosaic', 'chromosome_partition'])
def test_multiparent_contribution_symmetry(k, mechanism):
    genomes = np.zeros((k, 2, 16), dtype=np.uint8)
    genomes[:k//2] = 1
    children, contributions = inherit(np.random.default_rng(178), genomes, np.tile(np.arange(k), (5000, 1)),
                                      (4, 4, 4, 4), .05, mechanism)
    assert abs(children.mean()-.5) < .01
    np.testing.assert_allclose(contributions.mean(axis=0), 32/k, atol=.15)
    assert (contributions > 0).all()


def test_dead_and_immature_persistent_ids_never_mate():
    cfg = EcoConfig(steps=1, survival_probability=1, senescence_rate=0, fecundity=4)
    state = ecology.initialize(cfg)
    state.birth_tick[:] = -4
    state.birth_tick[1] = -cfg.max_age
    state.birth_tick[2] = 0
    class Mortality:
        def random(self, size):
            result = np.zeros(size)
            result[0] = 1
            return result
    state.rngs['mortality'] = Mortality()
    ecology.step(state)
    assert state.parentage
    assert not any(parent in (0, 1, 2) for r in state.parentage for parent in r['parents'])


def assert_ledgers(state):
    for row in state.ledger:
        assert row['end'] == row['start']-row['survival_deaths']-row['maintenance_deaths']-row['capacity_adult_deaths']+row['realized_newborns']
        assert row['raw_newborns'] == row['funded_newborns']+row['resource_rejected']
        assert row['funded_newborns'] == row['realized_newborns']+row['capacity_newborn_deaths']
        assert row['sexual_newborns'] <= row['raw_newborns']
    for row in state.resource_ledger:
        assert abs(row['before']+row['renewal']-row['overflow']-row['maintenance']-row['offspring']-row['after']) < 1e-7
        assert row['after'] >= 0


@pytest.mark.parametrize('mechanism', ['locus_mosaic', 'chromosome_partition'])
@pytest.mark.parametrize('scope', ['within_strategy', 'all_mixing'])
def test_demography_eligibility_and_accounting(mechanism, scope):
    cfg = EcoConfig(steps=30, multiparent_mechanism=mechanism, compatibility_scope=scope)
    state = ecology.advance(ecology.initialize(cfg))
    assert_ledgers(state)
    assert len(state.ids) <= cfg.capacity
    assert len(set(state.ids)) == len(state.ids)
    assert state.parentage
    assert {r['strategy'] for r in state.parentage} == set(STRATEGIES)
    assert any(len(set(r['parent_birth_ticks'])) > 1 for r in state.parentage if len(r['parents']) > 1)
    assert any(min(r['parent_birth_ticks']) < 0 <= max(r['parent_birth_ticks'])
               for r in state.parentage if len(r['parents']) > 1)
    for row in state.parentage:
        assert len(set(row['parents'])) == len(row['parents'])
        assert all(row['mating_tick']-birth >= cfg.maturity_age for birth in row['parent_birth_ticks'])
        assert all(row['mating_tick']-birth < cfg.max_age for birth in row['parent_birth_ticks'])
        assert sum(row['contributed_copies']) == 2*cfg.loci
        if len(row['parents']) > 1:
            assert 'clone' not in row['parent_strategies']
        if scope == 'within_strategy':
            assert all(s == row['strategy'] for s in row['parent_strategies'])


def test_death_before_breeding_and_no_restoration():
    cfg = EcoConfig(steps=30, survival_probability=0, log_every=17)
    state = ecology.advance(ecology.initialize(cfg))
    assert state.tick == 1 and len(state.ids) == 0
    assert not state.parentage
    assert set(state.extinct.values()) == {1}
    assert state.metrics[-1]['tick'] == 1
    assert_ledgers(state)


def test_immaturity_prevents_all_reproduction():
    state = ecology.initialize(EcoConfig(steps=1, survival_probability=1, senescence_rate=0))
    state.birth_tick[:] = 0
    ecology.step(state)
    assert not state.parentage
    assert sum(state.cumulative['attempts']) == 0


def test_resources_and_uniform_capacity_culling_accounted():
    for config in [EcoConfig(steps=10, initial_resources=0, resource_renewal=0, survival_probability=1, senescence_rate=0),
                   EcoConfig(steps=10, capacity=224, survival_probability=1, senescence_rate=0,
                             resource_capacity=10000, initial_resources=10000, resource_renewal=10000, fecundity=4)]:
        state = ecology.advance(ecology.initialize(config))
        assert_ledgers(state)
        if config.resource_renewal == 0:
            assert not len(state.ids)
            assert sum(state.cumulative['maintenance_deaths']) == 224
        else:
            assert sum(state.cumulative['capacity_newborn_deaths']) > 0
            assert sum(state.cumulative['capacity_adult_deaths']) > 0


def test_fallback_and_obligate_mate_failure():
    cfg = EcoConfig(steps=1, initial_counts=(0, 1, 1, 1, 1, 1, 1), capacity=20,
                    fecundity=4, survival_probability=1, senescence_rate=0, facultative_probability=1,
                    stress_threshold=1)
    state = ecology.initialize(cfg)
    state.birth_tick[:] = -4
    ecology.step(state)
    assert all(r['strategy'] in ('facultative', 'periodic', 'stress') for r in state.parentage)
    assert state.parentage and all(r['fallback'] and len(r['parents']) == 1 for r in state.parentage)
    assert sum(state.cumulative['mate_failures']) > 0


def test_zero_encounters_and_no_fallback_blocks_sex():
    cfg = EcoConfig(steps=5, encounter_probability=0, facultative_fallback=False,
                    facultative_probability=1, period=1, stress_threshold=1)
    state = ecology.advance(ecology.initialize(cfg))
    assert all(r['strategy'] == 'clone' for r in state.parentage)
    assert sum(state.cumulative['encounter_failures']) > 0


def test_neutral_no_cost_first_step_has_equal_output_opportunities():
    outcomes = []
    for strategy in (0, 1, 5, 6):
        initial = [0]*7
        initial[strategy] = 224
        cfg = EcoConfig(steps=1, initial_counts=tuple(initial), capacity=1000,
                        selection_coefficient=0, parasite='none', mating_cost=0, extra_parent_cost=0,
                        survival_probability=1, senescence_rate=0)
        state = ecology.initialize(cfg)
        state.birth_tick[:] = -4
        ecology.step(state)
        outcomes.append((sum(state.cumulative['attempts']), sum(state.cumulative['raw_newborns']), len(state.ids)))
    assert len(set(outcomes)) == 1


def test_environment_stream_independent_of_reproduction_and_costs():
    cfg = EcoConfig(steps=20, environment='autocorrelated')
    first = ecology.initialize(cfg)
    second = ecology.initialize(replace(cfg, mating_cost=.7, initial_counts=(224, 0, 0, 0, 0, 0, 0)))
    np.testing.assert_array_equal(first.environment, second.environment)
    np.testing.assert_array_equal(first.genomes, second.genomes)
    assert not np.array_equal(first.environment[0], first.environment[-1])


def test_modifier_inheritance_and_mutation_bounds():
    cfg = EcoConfig(steps=15, initial_counts=(0, 0, 224, 0, 0, 0, 0), modifier_mutation_rate=1, modifier_step=.5)
    state = ecology.advance(ecology.initialize(cfg))
    assert ((state.mix_probability >= 0) & (state.mix_probability <= 1)).all()
    assert np.any(state.mix_probability != cfg.facultative_probability)


@pytest.mark.parametrize('change', [dict(initial_counts=[1]), dict(capacity=100), dict(maturity_age=20),
    dict(survival_probability=float('nan')), dict(offspring_resource_cost=0), dict(fecundity=8),
    dict(compatibility_matrix=[[1]]), dict(compatibility_matrix=[[True, False], [True, True]]),
    dict(multiparent_mechanism='magic'), dict(environment='random'), dict(parasite='unknown'),
    dict(steps=1000000), dict(chromosome_lengths=[8], multiparent_mechanism='chromosome_partition')])
def test_invalid_eco_config(change):
    with pytest.raises(ValueError):
        EcoConfig(**change)
