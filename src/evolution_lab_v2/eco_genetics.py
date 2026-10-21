"""Anchored distinct mating groups and explicitly hypothetical poly-parent inheritance."""
import numpy as np

from .genetics import gametes


def anchored_uniform_groups(rng, pool, focal, needed):
    """Uniform conditional distinct mates in O(births*k²), without N² tables."""
    pool = np.asarray(pool, dtype=np.int64)
    focal = np.asarray(focal, dtype=np.int64)
    if len(pool) < needed or needed < 1:
        raise ValueError("Insufficient breeders")
    if np.any(pool[1:] <= pool[:-1]) or not np.isin(focal, pool).all():
        raise ValueError("Pool must be sorted unique indexes containing all focal breeders")
    groups = np.empty((len(focal), needed), dtype=np.int64)
    groups[:, 0] = np.searchsorted(pool, focal)
    for col in range(1, needed):
        draw = rng.integers(0, len(pool) - col, size=len(focal))
        excluded = np.sort(groups[:, :col], axis=1)
        for j in range(col):
            draw += draw >= excluded[:, j]
        groups[:, col] = draw
    return pool[groups]


def compatible_groups(rng, pool, focal, needed, mating_types, matrix):
    """Sequential uniform draws among currently pairwise-compatible candidates.

    Greedy paths can fail even when another group exists. This is an explicit
    encounter mechanism, not an exhaustive feasible-group solver.
    """
    if np.asarray(matrix).all():
        if len(pool) < needed:
            return np.full((len(focal), needed), -1, dtype=np.int64)
        return anchored_uniform_groups(rng, pool, focal, needed)
    groups = np.full((len(focal), needed), -1, dtype=np.int64)
    matrix = np.asarray(matrix, dtype=bool)
    for row, first in enumerate(focal):
        groups[row, 0] = first
        available = np.asarray(pool)[np.asarray(pool) != first]
        for col in range(1, needed):
            candidates = available[matrix[mating_types[first], mating_types[available]]]
            for previous in groups[row, 1:col]:
                candidates = candidates[matrix[mating_types[previous], mating_types[candidates]]]
            if len(candidates) == 0:
                groups[row] = -1
                break
            chosen = int(rng.choice(candidates))
            groups[row, col] = chosen
            available = available[available != chosen]
    return groups


def inherit(rng, genomes, groups, chromosome_lengths, rate, mechanism):
    """Return diploid offspring and number of inherited allele copies per parent."""
    births, needed = groups.shape
    loci = sum(chromosome_lengths)
    if needed == 1:
        return genomes[groups[:, 0]].copy(), np.full((births, 1), 2*loci, dtype=np.int64)
    contributions = np.zeros((births, needed), dtype=np.int64)
    if needed == 2:
        children = np.stack([gametes(rng, genomes[groups[:, i]], chromosome_lengths, rate)
                             for i in range(2)], axis=1)
        contributions[:] = loci
        return children, contributions
    if needed not in (4, 8):
        raise ValueError("Supported contributor counts are 1/2/4/8")
    if 2*loci < needed:
        raise ValueError("Too few allele-copy positions for all genetic parents")
    donor_gametes = np.stack([gametes(rng, genomes[groups[:, i]], chromosome_lengths, rate)
                             for i in range(needed)], axis=1)
    if mechanism == "locus_mosaic":
        which = rng.integers(0, needed, size=(births, 2, loci))
        # Reserve one random allele-copy slot for each donor, then allocate all
        # remaining slots uniformly. This explicit coverage constraint guarantees
        # k actual genetic contributors; it is not unconstrained independent mixing.
        positions = np.argsort(rng.random((births, 2*loci)), axis=1)[:, :needed]
        which.reshape(births, 2*loci)[np.arange(births)[:, None], positions] = np.arange(needed)
    elif mechanism == "chromosome_partition":
        chromosomes = len(chromosome_lengths)
        if 2*chromosomes % needed or len(set(chromosome_lengths)) != 1:
            raise ValueError("Cannot balance intact chromosomes among these parents")
        # Hypothetical fusion/reduction: allocate intact chromosomes from k
        # haploid gametes to a diploid output, equally, without changing ploidy.
        order = np.argsort(rng.random((births, needed)), axis=1)
        assignments = np.empty((births, 2, chromosomes), dtype=np.int64)
        for c in range(chromosomes):
            assignments[:, 0, c] = order[:, (2*c) % needed]
            assignments[:, 1, c] = order[:, (2*c+1) % needed]
        which = np.repeat(assignments, chromosome_lengths, axis=2)
    else:
        raise ValueError("Unknown multiparent mechanism")
    children = donor_gametes[np.arange(births)[:, None, None], which, np.arange(loci)[None, None, :]]
    for donor in range(needed):
        contributions[:, donor] = (which == donor).sum(axis=(1, 2))
    return children.copy(), contributions
