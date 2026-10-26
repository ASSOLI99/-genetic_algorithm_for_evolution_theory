# Extinction-accounting diagnostic protocol — 2026-10-26

This diagnostic is frozen before its new replicate results. It audits arithmetic and sensitivity of the existing model; it neither tunes parameters to rescue a strategy nor empirically validates the model. The engine and historical baseline remain unchanged. Generated records stay local.

## Design and endpoints

`configs/survival_audit.json` declares eight new seeds, 41001..41008, three environments, 800 census updates and capacity 336. Every run has total initial census 224, binary diploid genome length 16, no parasites or catastrophes, zero added mating/contributor costs, encounter probability one and the existing life history/resource defaults. These settings reproduce the default GUI mechanisms at this declared size/horizon; they are not the user's exact smaller-census run. Seven prespecified cases give 168 runs:

- `seven_default`: seven programs, 32 founders each, ordinary selection and within-program mating.
- `seven_neutral`: same with selection zero; mutation/recombination continue but nuclear genotype has no performance effect.
- `seven_neutral_pooled`: neutral, with contributors drawn across mixing-capable programs. Permanent clones remain excluded as donors. This is the engine's declared alternative compatibility control.
- `pair_default`: clones and obligate two-parent reproduction only, 112 founders each.
- `isolated_clone` and `isolated_two_parent`: one established program, 224 founders, otherwise identical environment/resource/life-history settings. These ask persistence without competition from other programs, not seven-way relative advantage.
- `seven_no_crossover`: seven default programs with adjacent-homolog switch probability zero. Independent chromosome assortment and segregation persist, so this is not a complete no-mixing control.

Primary diagnostic endpoint: per-program census extinction by update 800, including every planned run. Report counts/denominators and Wilson 95% intervals. Secondary: final abundance, population-wide extinction, exact census extinction times, restricted observed persistence `min(T,800)` with censoring flags, mate/encounter failure, births, losses by cause and population/resource conservation. Initially absent programs are outside risk sets. Final counts compare default/neutral in seed-paired blocks with descriptive percentile bootstrap 95% intervals (5,000 resamples, analysis seed declared separately). No familywise testing or universal winner is inferred. Eight seeds have wide uncertainty and this design is not a power analysis.

Seeds pair founder/exogenous draws where equal-size configurations permit. Demographic RNG consumption can diverge, so deaths and mating are not claimed to stay individually paired. Environment/seasonality co-vary in the existing engine; these comparisons do not isolate those mechanisms. The input file, fully expanded run configurations, exact tool/protocol hashes and runtime/source signature are saved before any run. Failed runs stop the audit; resume verifies the immutable plan and completed artifacts. Timing of the first planned run is a cost measurement, retained in the analysis rather than discarded. No outcome is omitted or chosen after inspection.

## Arithmetic checks and computational limits

The independent checker reads CSV ledgers and checkpoint arrays. It verifies population change, each birth-funding/recruitment decomposition, cumulative counters, exact first-zero census events, end populations, resources including catastrophe stock loss, and every recorded artifact digest. Existing user exports can be inspected without bypassing checkpoint execution signatures: reading non-pickle arrays/metadata is an audit of stored values, not a cross-version resume claim.

Analytical tests check age-specific survival frequencies, lifespan/maturity timing, equal neutral opportunity rates across all seven programs when mates/resources/census are sufficient, and the uniform adult/newborn census lottery. A life table reports low-density expected focal recruited offspring under constant performance, ignoring competition and assuming sufficient compatible partners; it is not an observed population growth estimate or a viability guarantee at rarity. Offspring first breed only after survival at each of ages 0,1,2 under default maturity 2.

Budget: 45,158,400 capacity-based individual updates and 722,534,400 locus updates, within existing aggregate guards. Parentage is off for the replicate batch and tested separately in the unit suite. Per-run checkpoint at update 400 and the end, with full ledgers and final genomes; metric sampling every 20 updates does not determine extinction timing. Runs execute sequentially. No million-individual experiment or calibrated geological simulation is attempted.

## Interpretation boundaries

Program labels are inherited from the focal reproducer, do not mutate between programs and receive no immigration. A lost program therefore cannot reappear. Survival probability .85 per update, maturity 2, senescence from age 8, maximum age 16, fecundity .65, resources and hard census regulation are synthetic assumptions. Birth opportunities depend on focal performance; additional donors are sampled uniformly, can participate repeatedly, and have no individual debit. Selection acts on fecundity rather than directly on age-survival. These choices can affect comparisons despite correct arithmetic. Mating types do not mean male/female roles; no actual sex-ratio cost is implemented. Four/eight-parent mechanics remain hypothetical, time is uncalibrated and there is no spatial migration or independently evolving pathogen population.

Correct numerical implementation is distinct from empirical adequacy. Explicit life cycles and density regulation require stated mechanisms ([Haller & Messer 2019](https://doi.org/10.1093/molbev/msy228)); species-specific demographic/genomic parameters and independent model checking are illustrated by [Adrion et al. 2020](https://elifesciences.org/articles/54967). Neither source calibrates the parameters used here. No conclusion that the simulation is “very close to reality” follows from passing these checks.
