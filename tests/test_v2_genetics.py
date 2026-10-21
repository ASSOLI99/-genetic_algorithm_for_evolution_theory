import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from evolution_lab_v2.genetics import choose_distinct_parents, gametes, log_viability


@given(n=st.integers(8, 80), needed=st.sampled_from([1, 2, 4, 8]), births=st.integers(0, 30))
@settings(max_examples=60, derandomize=True)
def test_parent_sampling_properties(n, needed, births):
    ids = np.arange(n, dtype=np.int64) * 3 + 400
    weights = np.arange(1, n + 1, dtype=float)
    groups = choose_distinct_parents(np.random.default_rng(12), ids, weights, births, needed)
    assert groups.shape == (births, needed)
    assert np.isin(groups, ids).all()
    assert all(len(np.unique(row)) == needed for row in groups)


def test_skewed_and_zero_weights():
    weights = np.full(50, .001/49)
    weights[0] = .999
    groups = choose_distinct_parents(np.random.default_rng(1), np.arange(50), weights, 200, 8)
    assert all(len(set(row)) == 8 for row in groups)
    groups = choose_distinct_parents(np.random.default_rng(1), np.arange(4), [0, 0, 1, 2], 200, 2)
    assert np.isin(groups, [2, 3]).all()


def test_unrepresentable_weight_support_rejected():
    with pytest.raises(ValueError, match="floating-point"):
        choose_distinct_parents(np.random.default_rng(1), [0, 1], [1e308, 1e-308], 2, 2)


@pytest.mark.parametrize("ids,w,b,k", [([0, 0], [1, 1], 1, 2), ([0, 1], [1, -1], 1, 1),
    ([0, 1], [1, float('nan')], 1, 1), ([0, 1], [1, 0], 1, 2), ([0, 1], [1, 1], -1, 2),
    ([0, 1], [1, 1], 1, 0), ([0, 1], [1], 1, 1)])
def test_invalid_sampling(ids, w, b, k):
    with pytest.raises(ValueError):
        choose_distinct_parents(np.random.default_rng(1), ids, w, b, k)


def test_weighted_ordered_pair_probabilities():
    # P(first=i, second=j) = w_i/W * w_j/(W-w_i), i != j.
    w = np.array([1., 2., 3.])
    groups = choose_distinct_parents(np.random.default_rng(8), np.arange(3), w, 30000, 2)
    for i in range(3):
        for j in range(3):
            if i == j:
                continue
            expected = w[i]/w.sum() * w[j]/(w.sum()-w[i])
            actual = ((groups[:, 0] == i) & (groups[:, 1] == j)).mean()
            se = np.sqrt(expected * (1-expected) / len(groups))
            assert abs(actual - expected) < 6 * se


def test_chromosomal_linkage_and_assortment():
    parents = np.zeros((8000, 2, 8), dtype=np.uint8)
    parents[:, 1] = 1
    g = gametes(np.random.default_rng(12), parents, (4, 4), 0)
    assert (g[:, :4] == g[:, :1]).all()
    assert (g[:, 4:] == g[:, 4:5]).all()
    assert abs((g[:, 0] != g[:, 4]).mean() - .5) < .03


def test_recombination_switch_probability():
    parents = np.zeros((8000, 2, 8), dtype=np.uint8)
    parents[:, 1] = 1
    g = gametes(np.random.default_rng(13), parents, (8,), .1)
    assert abs((g[:, 1:] != g[:, :-1]).mean() - .1) < .01


def test_dominance_and_multiplicative_viability():
    genomes = np.array([[[0], [0]], [[0], [1]], [[1], [1]]], dtype=np.uint8)
    np.testing.assert_allclose(np.exp(log_viability(genomes, .2, .5)), [1, .9, .8])
    np.testing.assert_allclose(np.exp(log_viability(np.repeat(genomes, 2, axis=2), .2, .5)), [1, .81, .64])
