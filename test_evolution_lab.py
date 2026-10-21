"""Run: python test_evolution_lab.py"""
import numpy as np
from evolution_lab_verified import choose_distinct_parents, simulate

def test_distinct_parents():
    rng = np.random.default_rng(12)
    ids = np.arange(30)
    w = np.ones(len(ids)) / len(ids)
    for k in (1, 2, 4, 8):
        group = choose_distinct_parents(rng, ids, w, 1000, k)
        assert group.shape == (1000, k)
        assert all(len(set(row)) == k for row in group), f'duplicate parent in k={k}'
    # Small-population path
    group = choose_distinct_parents(rng, np.arange(8), np.ones(8)/8, 20, 8)
    assert all(len(set(row)) == 8 for row in group)
    print('PASS: each child has the requested number of distinct parents')

def test_generations():
    records = simulate(seed=102026, generations=100, capacity=250, mode='established', log_every=10)
    assert records[-1]['mixed_age_matings'] > 0, records[-1]
    print('PASS: breeders of different birth generations were paired: ',records[-1]['mixed_age_matings'])

if __name__ == '__main__':
    test_distinct_parents()
    test_generations()
