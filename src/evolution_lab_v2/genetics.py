"""Diploid linked inheritance and finite weighted sampling, without collision repair."""
import numpy as np


def choose_distinct_parents(rng, indexes, weights, births, needed):
    """Sequential probability-proportional-to-weight draws without replacement.

    Each offspring samples independently. Chunking bounds temporary space at
    128 * eligible breeders; zero weights are never selected. No rejection loop.
    """
    ids = np.asarray(indexes)
    w = np.asarray(weights, dtype=np.float64)
    if ids.ndim != 1 or ids.dtype.kind not in "iu" or len(np.unique(ids)) != len(ids):
        raise ValueError("indexes must be unique integer identifiers")
    if w.shape != ids.shape or not np.isfinite(w).all() or (w < 0).any():
        raise ValueError("weights must be finite, nonnegative and match indexes")
    if type(births) is not int or births < 0 or type(needed) is not int or needed < 1:
        raise ValueError("births must be nonnegative and needed positive integers")
    if np.count_nonzero(w) < needed:
        raise ValueError("Insufficient positive-weight eligible parents")
    w = w / w.max()  # avoid overflow when summing finite large weights
    if np.count_nonzero(w) < needed:
        raise ValueError("Weight dynamic range exceeds floating-point support")
    result = np.empty((births, needed), dtype=np.int64)
    for start in range(0, births, 128):
        size = min(128, births - start)
        remaining = np.broadcast_to(w, (size, len(w))).copy()
        for col in range(needed):
            cumulative = remaining.cumsum(axis=1)
            total = cumulative[:, -1]
            draw = np.minimum(rng.random(size) * total, np.nextafter(total, 0))
            picked = (cumulative > draw[:, None]).argmax(axis=1)
            result[start:start + size, col] = ids[picked]
            remaining[np.arange(size), picked] = 0
    return result


def gametes(rng, parental_genomes, chromosome_lengths, recombination_rate):
    """One haploid gamete per diploid: independent chromosome assortment.

    Homolog switches at each adjacent-locus boundary have probability r.
    This is a discrete map, without interference or gene conversion.
    """
    count = len(parental_genomes)
    result = np.empty((count, sum(chromosome_lengths)), dtype=np.uint8)
    offset = 0
    for length in chromosome_lengths:
        initial = rng.integers(0, 2, size=count, dtype=np.uint8)
        switches = rng.random((count, length - 1)) < recombination_rate
        homologs = np.empty((count, length), dtype=np.uint8)
        homologs[:, 0] = initial
        if length > 1:
            homologs[:, 1:] = initial[:, None] ^ (np.cumsum(switches, axis=1) % 2).astype(np.uint8)
        positions = np.arange(offset, offset + length)
        result[:, offset:offset + length] = parental_genomes[np.arange(count)[:, None], homologs, positions]
        offset += length
    return result


def log_viability(genomes, selection_coefficient, dominance):
    dosage = genomes.sum(axis=1)
    penalty = np.where(dosage == 2, selection_coefficient,
                       np.where(dosage == 1, dominance * selection_coefficient, 0.0))
    return np.log1p(-penalty).sum(axis=1)
