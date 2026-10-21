"""NonWF, overlapping-cohort comparison engine with explicit accounting."""
from dataclasses import dataclass, field
import hashlib

import numpy as np

from .eco_config import EcoConfig, PARENTS, STRATEGIES
from .eco_genetics import compatible_groups, inherit
from .genetics import log_viability

STREAMS = ("environment", "founders", "mortality", "mating", "genetics", "resources", "parasite", "modifier")
ARRAYS = ("genomes", "ids", "strategy", "birth_tick", "mating_type", "mix_probability")
COUNTERS = ("survival_deaths", "maintenance_deaths", "attempts", "mate_failures", "encounter_failures",
            "fallback_births", "raw_newborns", "funded_newborns", "resource_rejected",
            "capacity_adult_deaths", "capacity_newborn_deaths", "realized_newborns",
            "sexual_newborns", "mixed_cohort_newborns", "selected_parent_slots", "positive_contributor_slots",
            "effort_spent", "offspring_resources")


@dataclass
class EcoState:
    config: EcoConfig
    tick: int
    genomes: np.ndarray
    ids: np.ndarray
    strategy: np.ndarray
    birth_tick: np.ndarray
    mating_type: np.ndarray
    mix_probability: np.ndarray
    environment: np.ndarray
    parasite: np.ndarray
    resources: float
    next_id: int
    rngs: dict
    founders: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)
    resource_ledger: list[dict] = field(default_factory=list)
    parentage: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    extinct: dict = field(default_factory=dict)
    established: dict = field(default_factory=dict)
    cumulative: dict = field(default_factory=dict)


def counts(state):
    return np.bincount(state.strategy, minlength=len(STRATEGIES))


def performance(state):
    cfg = state.config
    # Allele 1 is beneficial when the environmental target is 1, deleterious
    # when it is 0; dominance applies to mismatching copies in either direction.
    mismatches = state.genomes ^ state.environment[state.tick][None, None, :]
    score = np.exp(log_viability(mismatches, cfg.selection_coefficient, cfg.dominance))
    if cfg.parasite != "none" and len(state.genomes):
        immunity = max(1, cfg.loci // 4)
        matching = (state.genomes[:, :, -immunity:] == state.parasite[None, None, :]).mean(axis=(1, 2))
        score *= np.exp(-cfg.parasite_strength * matching)
    return score


def update_events(state):
    current = counts(state)
    for s, name in enumerate(STRATEGIES):
        if state.config.initial_counts[s] == 0:
            continue
        if current[s] == 0 and name not in state.extinct:
            state.extinct[name] = state.tick
            state.events.append({"tick": state.tick, "event": "strategy_extinction", "strategy": name})
        if current[s] >= state.config.establishment_size and name not in state.established:
            state.established[name] = state.tick
            state.events.append({"tick": state.tick, "event": "threshold_reached", "strategy": name,
                                 "threshold": state.config.establishment_size})
    if len(state.ids) == 0 and not any(e["event"] == "population_extinction" for e in state.events):
        state.events.append({"tick": state.tick, "event": "population_extinction", "strategy": "all"})
    if (current > 0).sum() == 1 and sum(n > 0 for n in state.config.initial_counts) > 1:
        name = STRATEGIES[int(np.flatnonzero(current)[0])]
        if not any(e["event"] == "strategy_fixation" for e in state.events):
            state.events.append({"tick": state.tick, "event": "strategy_fixation", "strategy": name})


def observe(state):
    score = performance(state)
    result = []
    for s, name in enumerate(STRATEGIES):
        mask = state.strategy == s
        n = int(mask.sum())
        genomes = state.genomes[mask]
        p = genomes.mean(axis=(0, 1)) if n else None
        age = state.tick - state.birth_tick[mask]
        d2 = []
        offset = 0
        if n:
            for length in state.config.chromosome_lengths:
                for locus in range(offset, offset+length-1):
                    joint = float((genomes[:, :, locus]*genomes[:, :, locus+1]).mean())
                    d2.append((joint-p[locus]*p[locus+1])**2)
                offset += length
        result.append({"tick": state.tick, "strategy": name, "population": n, "total": len(state.ids),
                       "share": n/len(state.ids) if len(state.ids) else None,
                       "mature": int((age >= state.config.maturity_age).sum()),
                       "mean_age": float(age.mean()) if n else None,
                       "mean_performance": float(score[mask].mean()) if n else None,
                       "gene_diversity": float((2*p*(1-p)).mean()) if n else None,
                       "heterozygosity": float((genomes[:, 0] != genomes[:, 1]).mean()) if n else None,
                       "adaptive_lag": float(np.abs(genomes.mean(axis=1)-state.environment[state.tick]).mean()) if n else None,
                       "mean_linked_D2": float(np.mean(d2)) if d2 else None,
                       "mean_mix_probability": float(state.mix_probability[mask].mean()) if n else None,
                       "resources": state.resources})
    return result


def initialize(config):
    children = np.random.SeedSequence(config.seed).spawn(len(STREAMS))
    rngs = {name: np.random.Generator(np.random.PCG64(seed)) for name, seed in zip(STREAMS, children)}
    env_rng = rngs["environment"]
    environment = np.empty((config.steps+1, config.loci), dtype=np.uint8)
    environment[0] = env_rng.integers(0, 2, config.loci, dtype=np.uint8)
    for t in range(1, config.steps+1):
        environment[t] = environment[t-1]
        if config.environment == "periodic" and t % config.environment_period == 0:
            environment[t] ^= 1
        elif config.environment == "autocorrelated":
            environment[t] ^= (env_rng.random(config.loci) < config.environment_flip_rate).astype(np.uint8)
    n = sum(config.initial_counts)
    rng = rngs["founders"]
    genomes = (rng.random((n, 2, config.loci)) < config.initial_frequency).astype(np.uint8)
    strategy = np.repeat(np.arange(len(STRATEGIES), dtype=np.int64), config.initial_counts)
    rng.shuffle(strategy)
    ages = rng.integers(0, min(config.max_age, config.maturity_age+4), n, dtype=np.int64)
    types = rng.integers(0, len(config.compatibility_matrix), n, dtype=np.int64)
    mix = np.where(strategy == 2, config.facultative_probability, 0.0)
    parasite = rngs["parasite"].integers(0, 2, max(1, config.loci//4), dtype=np.uint8)
    state = EcoState(config, 0, genomes, np.arange(n, dtype=np.int64), strategy, -ages, types, mix,
                     environment, parasite, config.initial_resources, n, rngs)
    state.founders = [{"id": int(i), "birth_tick": int(b), "strategy": STRATEGIES[int(s)], "mating_type": int(mt)}
                      for i, b, s, mt in zip(state.ids, state.birth_tick, state.strategy, state.mating_type)]
    state.cumulative = {name: [0.0]*len(STRATEGIES) for name in COUNTERS}
    update_events(state)
    state.metrics.extend(observe(state))
    return state


def subset(state, mask):
    for name in ARRAYS:
        setattr(state, name, getattr(state, name)[mask])


def intended_parents(state, breeders, scores):
    cfg = state.config
    strategy = state.strategy[breeders]
    needed = np.asarray(PARENTS, dtype=np.int64)[strategy]
    mix = state.rngs["mating"].random(len(breeders)) < state.mix_probability[breeders]
    needed[(strategy == 2) & ~mix] = 1
    if state.tick % cfg.period:
        needed[strategy == 3] = 1
    needed[(strategy == 4) & (scores[breeders] >= cfg.stress_threshold)] = 1
    return needed


def step(state):
    cfg = state.config
    if state.tick >= cfg.steps:
        raise ValueError("Configured demographic horizon reached")
    start_counts = counts(state)
    stats = {name: np.zeros(len(STRATEGIES), dtype=float) for name in COUNTERS}

    def tally(name, strategies, weights=None):
        stats[name] += np.bincount(strategies, weights=weights, minlength=len(STRATEGIES))

    # Host-responsive parasite dynamics, on a separate stream. No regime-dependent
    # calls to mortality/mating/environment RNGs.
    immunity = max(1, cfg.loci//4)
    if cfg.parasite == "tracking" and state.tick and state.tick % cfg.parasite_period == 0 and len(state.ids):
        state.parasite = (state.genomes[:, :, -immunity:].mean(axis=(0, 1)) >= .5).astype(np.uint8)
        state.parasite ^= (state.rngs["parasite"].random(immunity) < cfg.parasite_noise).astype(np.uint8)
    scores = performance(state)
    ages = state.tick - state.birth_tick
    survival = cfg.survival_probability * np.exp(-cfg.senescence_rate*np.maximum(0, ages-cfg.senescence_age))
    live = (state.rngs["mortality"].random(len(state.ids)) < survival) & (ages < cfg.max_age)
    tally("survival_deaths", state.strategy[~live])
    subset(state, live)
    scores = scores[live]

    resources_before = state.resources
    renewal = cfg.resource_renewal
    if cfg.environment != "static":
        renewal *= 1 + cfg.seasonal_amplitude*np.sin(2*np.pi*state.tick/cfg.environment_period)
    available = min(cfg.resource_capacity, state.resources+renewal)
    overflow = max(0.0, state.resources+renewal-cfg.resource_capacity)
    maintenance_slots = len(state.ids) if cfg.maintenance_cost == 0 else min(len(state.ids), int(available/cfg.maintenance_cost))
    maintained = np.zeros(len(state.ids), dtype=bool)
    maintained[state.rngs["resources"].choice(len(state.ids), maintenance_slots, replace=False)] = True
    tally("maintenance_deaths", state.strategy[~maintained])
    subset(state, maintained)
    scores = scores[maintained]
    maintenance_spent = len(state.ids)*cfg.maintenance_cost
    available -= maintenance_spent

    breeders = np.flatnonzero(state.tick-state.birth_tick >= cfg.maturity_age)
    required = intended_parents(state, breeders, scores)
    cost = 1 + np.where(required > 1, cfg.mating_cost+cfg.extra_parent_cost*(required-1), 0)
    # Equal expected effort budget: mean opportunities * intended effort =
    # fecundity * performance. This is not a hard per-individual energy bound.
    opportunities = state.rngs["mating"].poisson(cfg.fecundity*scores[breeders]/cost)
    if int(opportunities.sum()) > 50000:
        raise ValueError("Attempt safety limit exceeded; no silent Poisson clipping")
    focal = np.repeat(breeders, opportunities)
    needed = np.repeat(required, opportunities)
    effort = np.repeat(cost, opportunities)
    tally("attempts", state.strategy[focal])
    tally("effort_spent", state.strategy[focal], effort)

    child_genomes, child_focal, child_types, child_mix, details = [], [], [], [], []
    # Interleave opportunities before grouping so resource allocation is never
    # based on strategy iteration order. Resource lotteries operate on all births.
    for s in range(len(STRATEGIES)):
        for k in (1, 2, 4, 8):
            anchors = focal[(state.strategy[focal] == s) & (needed == k)]
            if not len(anchors):
                continue
            if k == 1:
                groups = anchors[:, None]
                fallback = np.zeros(len(groups), dtype=bool)
            else:
                pool = breeders[state.strategy[breeders] == s] if cfg.compatibility_scope == "within_strategy" else breeders[state.strategy[breeders] != 0]
                groups = compatible_groups(state.rngs["mating"], pool, anchors, k, state.mating_type, cfg.compatibility_matrix)
                compatible = (groups >= 0).all(axis=1)
                encounters = state.rngs["mating"].random(len(anchors)) < cfg.encounter_probability**(k-1)
                tally("mate_failures", np.full(int((~compatible).sum()), s, dtype=np.int64))
                tally("encounter_failures", np.full(int((compatible & ~encounters).sum()), s, dtype=np.int64))
                successful = compatible & encounters
                failed_anchors = anchors[~successful]
                groups = groups[successful]
                fallback = np.zeros(len(groups), dtype=bool)
                if cfg.facultative_fallback and s in (2, 3, 4) and len(failed_anchors):
                    # Process the clonal fallback separately; the original search
                    # effort remains charged, without a second construction fee.
                    clones, contributed = inherit(state.rngs["genetics"], state.genomes, failed_anchors[:, None], cfg.chromosome_lengths, cfg.recombination_rate, cfg.multiparent_mechanism)
                    child_genomes.append(clones)
                    child_focal.append(failed_anchors)
                    child_types.append(state.mating_type[failed_anchors].copy())
                    child_mix.append(state.mix_probability[failed_anchors].copy())
                    details.extend([(int(a), [int(a)], [2*cfg.loci], 1, True) for a in failed_anchors])
                    tally("fallback_births", np.full(len(failed_anchors), s, dtype=np.int64))
                    tally("selected_parent_slots", np.full(len(failed_anchors), s, dtype=np.int64))
                    tally("positive_contributor_slots", np.full(len(failed_anchors), s, dtype=np.int64))
            if not len(groups):
                continue
            children, contributed = inherit(state.rngs["genetics"], state.genomes, groups, cfg.chromosome_lengths, cfg.recombination_rate, cfg.multiparent_mechanism)
            anchors = groups[:, 0]
            which_type = state.rngs["genetics"].integers(0, groups.shape[1], len(groups))
            child_genomes.append(children)
            child_focal.append(anchors)
            child_types.append(state.mating_type[groups[np.arange(len(groups)), which_type]])
            child_mix.append(state.mix_probability[anchors].copy())
            tally("selected_parent_slots", state.strategy[anchors], np.full(len(anchors), k))
            tally("positive_contributor_slots", state.strategy[anchors], (contributed > 0).sum(axis=1))
            if k > 1:
                tally("sexual_newborns", state.strategy[anchors])
                tally("mixed_cohort_newborns", state.strategy[anchors][np.ptp(state.birth_tick[groups], axis=1) > 0])
            details.extend([(int(a), row.tolist(), contribution.tolist(), k, False)
                            for a, row, contribution in zip(anchors, groups, contributed)])

    raw = sum(len(x) for x in child_genomes)
    if raw:
        children = np.concatenate(child_genomes)
        anchors = np.concatenate(child_focal)
        offspring_s = state.strategy[anchors].copy()
        offspring_types = np.concatenate(child_types)
        offspring_mix = np.concatenate(child_mix)
        children ^= (state.rngs["genetics"].random(children.shape) < cfg.mutation_rate).astype(np.uint8)
        change = (offspring_s == 2) & (state.rngs["modifier"].random(raw) < cfg.modifier_mutation_rate)
        proposed = offspring_mix[change]+state.rngs["modifier"].normal(0, cfg.modifier_step, int(change.sum()))
        offspring_mix[change] = 1-np.abs((proposed % 2)-1)  # reflecting boundaries
    else:
        children = np.empty((0, 2, cfg.loci), dtype=np.uint8)
        offspring_s = offspring_types = np.empty(0, dtype=np.int64)
        offspring_mix = np.empty(0, dtype=float)
    tally("raw_newborns", offspring_s)
    funded_count = min(raw, int(max(0, available)/cfg.offspring_resource_cost))
    funded = np.zeros(raw, dtype=bool)
    funded[state.rngs["resources"].choice(raw, funded_count, replace=False)] = True
    tally("funded_newborns", offspring_s[funded])
    tally("resource_rejected", offspring_s[~funded])
    tally("offspring_resources", offspring_s[funded], np.full(funded_count, cfg.offspring_resource_cost))
    offspring_spent = funded_count*cfg.offspring_resource_cost
    state.resources = max(0.0, available-offspring_spent)
    adults = len(state.ids)
    kept = np.ones(adults+funded_count, dtype=bool)
    if len(kept) > cfg.capacity:
        kept[:] = False
        kept[state.rngs["resources"].choice(len(kept), cfg.capacity, replace=False)] = True
    tally("capacity_adult_deaths", state.strategy[~kept[:adults]])
    recruitment = np.zeros(raw, dtype=bool)
    recruitment[np.flatnonzero(funded)] = kept[adults:]
    tally("capacity_newborn_deaths", offspring_s[funded & ~recruitment])
    tally("realized_newborns", offspring_s[recruitment])
    # All successfully formed candidate offspring have lineage records, including
    # candidates rejected for resources or capacity; IDs are never reused.
    candidate_ids = np.arange(state.next_id, state.next_id+raw, dtype=np.int64)
    if cfg.record_parentage and len(state.parentage)+raw > cfg.max_logged_births:
        raise ValueError("Parentage storage limit exceeded; resume requires reviewing the run size")
    for i, (anchor, group, contribution, k, is_fallback) in enumerate(details):
        if cfg.record_parentage:
            state.parentage.append({"offspring_id": int(candidate_ids[i]), "birth_tick": state.tick+1,
                                   "mating_tick": state.tick, "strategy": STRATEGIES[int(offspring_s[i])],
                                   "parents": state.ids[group].tolist(), "parent_birth_ticks": state.birth_tick[group].tolist(),
                                   "parent_strategies": [STRATEGIES[int(x)] for x in state.strategy[group]],
                                   "parent_mating_types": state.mating_type[group].tolist(),
                                   "contributed_copies": contribution, "requested_parents": PARENTS[int(offspring_s[i])] if is_fallback else k,
                                   "fallback": is_fallback, "funded": bool(funded[i]), "recruited": bool(recruitment[i])})
    for name, values in (("genomes", children[funded]), ("ids", candidate_ids[funded]), ("strategy", offspring_s[funded]),
                         ("birth_tick", np.full(funded_count, state.tick+1, dtype=np.int64)),
                         ("mating_type", offspring_types[funded]), ("mix_probability", offspring_mix[funded])):
        setattr(state, name, np.concatenate([getattr(state, name), values]))
    subset(state, kept)
    state.next_id += raw
    state.tick += 1
    end_counts = counts(state)
    for s, name in enumerate(STRATEGIES):
        balance = start_counts[s]-stats["survival_deaths"][s]-stats["maintenance_deaths"][s]-stats["capacity_adult_deaths"][s]+stats["realized_newborns"][s]
        if balance != end_counts[s]:
            raise ValueError("Population accounting violated")
        row = {"tick": state.tick, "strategy": name, "start": int(start_counts[s]), "end": int(end_counts[s])}
        for counter in COUNTERS:
            row[counter] = float(stats[counter][s]) if counter in ("effort_spent", "offspring_resources") else int(stats[counter][s])
            state.cumulative[counter][s] += float(stats[counter][s])
        state.ledger.append(row)
    residual = resources_before+renewal-overflow-maintenance_spent-offspring_spent-state.resources
    if abs(residual) > 1e-7:
        raise ValueError("Resource accounting violated")
    state.resource_ledger.append({"tick": state.tick, "before": resources_before, "renewal": float(renewal),
                                  "overflow": float(overflow), "maintenance": maintenance_spent,
                                  "offspring": offspring_spent, "after": state.resources})
    update_events(state)
    if state.tick % cfg.log_every == 0 or state.tick == cfg.steps or len(state.ids) == 0:
        state.metrics.extend(observe(state))


def advance(state, until=None, checkpoint=None):
    target = state.config.steps if until is None else until
    if type(target) is not int or not state.tick <= target <= state.config.steps:
        raise ValueError("Invalid demographic target tick")
    saved = None
    while state.tick < target and len(state.ids):
        step(state)
        if checkpoint and state.tick % state.config.checkpoint_every == 0:
            checkpoint(state)
            saved = state.tick
    if checkpoint and saved != state.tick:
        checkpoint(state)
    return state


def state_digest(state):
    digest = hashlib.sha256()
    for name in ARRAYS:
        digest.update(name.encode())
        digest.update(getattr(state, name).tobytes())
    return digest.hexdigest()
