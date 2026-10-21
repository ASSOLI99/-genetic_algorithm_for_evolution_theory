"""Nonoverlapping, fixed-census diploid reference. No ecological persistence claims."""
from dataclasses import dataclass, field
import numpy as np

from .config import Config
from .genetics import choose_distinct_parents, gametes, log_viability


@dataclass
class State:
    config: Config
    generation: int
    genomes: np.ndarray
    rng: np.random.Generator
    records: list[dict] = field(default_factory=list)
    parentage: list[np.ndarray] = field(default_factory=list)


def observe(state):
    genomes, cfg = state.genomes, state.config
    p = genomes.mean(axis=(0, 1))
    return {"generation": state.generation, "population": len(genomes),
            "mean_allele_frequency": float(p.mean()),
            "gene_diversity": float((2 * p * (1 - p)).mean()),
            "observed_heterozygosity": float((genomes[:, 0] != genomes[:, 1]).mean()),
            "allele_one_copies_per_individual": float(genomes.sum(axis=(1, 2)).mean()),
            "mean_viability_score": float(np.exp(log_viability(genomes, cfg.selection_coefficient, cfg.dominance)).mean()),
            "realized_offspring": 0 if state.generation == 0 else cfg.population_size,
            "adult_deaths": 0 if state.generation == 0 else cfg.population_size,
            "allele_frequencies": p.tolist()}


def initialize(config):
    rng = np.random.Generator(np.random.PCG64(config.seed))
    genomes = (rng.random((config.population_size, 2, config.loci)) < config.initial_frequency).astype(np.uint8)
    state = State(config, 0, genomes, rng)
    state.records.append(observe(state))
    return state


def step(state):
    cfg = state.config
    if state.generation >= cfg.generations:
        raise ValueError("Configured final generation already reached")
    log_w = log_viability(state.genomes, cfg.selection_coefficient, cfg.dominance)
    weights = np.exp(log_w - log_w.max())
    needed = 1 if cfg.reproduction == "clone" else 2
    parents = choose_distinct_parents(state.rng, np.arange(cfg.population_size), weights,
                                      cfg.population_size, needed)
    if needed == 1:
        children = state.genomes[parents[:, 0]].copy()
    else:
        children = np.stack([gametes(state.rng, state.genomes[parents[:, i]],
                                     cfg.chromosome_lengths, cfg.recombination_rate) for i in range(2)], axis=1)
    children ^= (state.rng.random(children.shape) < cfg.mutation_rate).astype(np.uint8)
    state.genomes = children
    state.generation += 1
    state.parentage.append(parents)
    if state.generation % cfg.log_every == 0 or state.generation == cfg.generations:
        state.records.append(observe(state))


def advance(state, until=None, checkpoint=None):
    target = state.config.generations if until is None else until
    if type(target) is not int or not state.generation <= target <= state.config.generations:
        raise ValueError("Target must be between current and configured final generation")
    last_saved = None
    while state.generation < target:
        step(state)
        if checkpoint and state.generation % state.config.checkpoint_every == 0:
            checkpoint(state)
            last_saved = state.generation
    if checkpoint and last_saved != state.generation:
        checkpoint(state)
    return state
