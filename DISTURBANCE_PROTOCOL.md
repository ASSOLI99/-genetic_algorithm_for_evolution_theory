# Catastrophe extension v0.3 — model and exploratory protocol

Date: 2026-10-26. Written before the catastrophe pilot. This extends the v0.2 life cycle in `ECO_MODEL.md` and exploratory inference in `ECO_PROTOCOL.md`. It defines synthetic disturbances, not a reconstruction of Earth's history. No strategy advantage is assumed. The pilot is a software/model exploration, not a powered confirmatory biological study.

## Implemented mechanisms and clock

`catastrophe_regime` is `none`, `bottleneck`, `drought` or `combined`. A Bernoulli onset occurs with `catastrophe_probability` per census update when the regime is active. With p=.02 the mean waiting time is 50 updates, not a guaranteed 50-update interval or 50 years. At most one onset occurs per update. Fixed time steps cannot resolve multiple within-step events; rate/timestep convergence is future work.

The eight v0.2 random streams retain their original SeedSequence child indices. Two appended PCG64 streams separate the exogenous onset schedule from per-individual catastrophe mortality. The full schedule is generated before simulation. Cost, population and reproduction histories cannot change future onset times. Scenarios with the same seed, horizon and hazard parameters share onsets; `none` suppresses them. Observed event counts stop at global extinction, although the stored full schedule includes the remaining planned horizon.

After ordinary stochastic/age mortality and before resource maintenance and breeding:

1. A bottleneck independently kills each currently surviving individual with the declared `catastrophe_mortality`. The probability is identical for all strategies, genotypes, sexes and ages; no sex class exists. Ordinary and catastrophe mortality are counted separately. Combined per-step survival, before resource/census regulation, is ordinary survival multiplied by catastrophe survival on an onset step.
2. Drought immediately removes `catastrophe_resource_loss` of the current stored food. It multiplies the otherwise applicable renewal by `catastrophe_renewal_factor` for `catastrophe_duration` updates, including the onset update. The stock loss precedes the current update's renewal. Seasonality, if enabled, is applied before the drought multiplier.
3. Overlapping droughts extend the active end to the maximum previous/new end. Renewal factors do not multiply again. Each onset can remove another fraction of remaining stock. The shared census capacity is not reduced by this mechanism.
4. The combined regime performs both operations. No individuals are restored after losses. Surviving mature compatible breeders of any birth cohort may reproduce under the existing rules. Starvation caused by drought is a maintenance death, distinct from direct catastrophe mortality.

The default `none` regime leaves demographic and nuclear inheritance draws unchanged. The controls include zero-effect shocks (mortality=0, stock loss=0, renewal factor=1) to test that adding an onset does not change other stochastic streams. Appended logging/configuration fields and checkpoint schema do change the output schema.

All events occur in one shared patch. This is a population bottleneck/food-supply mechanism; it does not physically simulate earthquakes, asteroid impacts, volcanoes, refuges, migration, atmosphere or temperature. Catastrophe mortality has no heritable resistance trait. The extension alone supplies no genetic benefit for any reproductive strategy. Trait-dependent stress and spatial refuges would be separately declared mechanisms and require new controls.

## Accounting and outputs

Population balance per strategy is:

`end = start - ordinary_deaths - catastrophe_deaths - maintenance_deaths - capacity_adult_deaths + recruited_newborns`.

Resource balance is:

`after = before - catastrophe_loss + actual_renewal - overflow - maintenance - offspring_construction`.

Both identities are checked every update. `ledger.csv` adds catastrophe deaths. `resources.csv` adds catastrophe stock loss and the renewal multiplier. `catastrophes.csv` logs every observed onset, all seven pre-shock counts, per-strategy direct deaths, pre/post-shock stock, and the drought end. `tick` is the end-of-update census tick (first update is logged as 1); `renewal_depressed_until_exclusive` refers to the zero-based update clock, so an onset in update 0 with duration 8 affects updates 0..7, recorded at census ticks 1..8.

Summary JSON records observed onset count and the full schedule digest. The comparison CSV includes mean direct catastrophe deaths per strategy, while the HTML/Markdown report shows observed exposure. Low event counts can reflect early global extinction and must not be interpreted as a lower planned hazard. Ordinary survival curves, final counts including extinction zeros, resource ledgers and lineage output remain available. Recovery-time inference with overlapping shocks and censoring is not yet implemented; trajectories permit descriptive inspection only.

Checkpoint schema is `demographic-2`: it includes the full schedule, independent RNG states, active drought end, event records and all prior history. Strict code/runtime/config checks remain. Old v0.2 checkpoints require their original code; they are not silently migrated. The original published v0.2 commit is `4141ee7bd6d53e0ddb3c66b875978d359263099b`. A byte-preserved local source copy was made before development so prior local runs can still be reviewed with the original implementation. The two historical baseline Python files and historical CSV remain unchanged.

## Predefined bounded pilot

`configs/catastrophe_pilot.json`: 16 scenarios × four independent replicate blocks = 64 runs, 400 census updates, initial 32 per strategy and capacity 336. A new master seed, 2026102601, is separate from the earlier main comparison. It crosses four catastrophe regimes × mating initiation costs [0,.2] × environments [static,autocorrelated]. Parasites are absent; extra-contributor cost is zero; compatibility is within strategy and the hypothetical multiparent rule is locus mosaic. These fixed choices are not a broad robustness claim.

Active hazards use p=.02, direct mortality .5, stock loss .75, renewal multiplier .25 and duration 8. Only the corresponding regime mechanisms act. These values were chosen for a bounded stress test, not measured from a species or geological record. The `none` control is included once per cost/environment setting; inactive parameter combinations are not duplicated as independent replicates. Matching seeds preserve founders, external environments and planned onset draws as applicable. Per-individual catastrophe mortality can diverge with demographics.

Full parentage recording is off in the pilot to bound storage. IDs, genetics, population/resource accounting, metrics, seeds and checkpoints are retained. `record_parentage=true` remains available for smaller validation runs. Disabling ancestry does not bound the still-growing ledgers, metrics, environment schedule or checkpoint size.

The unchanged exploratory primary endpoint is final abundance at the fixed horizon. Extinction curves, direct catastrophe deaths, births and resource use are secondary. Existing bootstrap intervals are descriptive/unadjusted; exact sign tests use Holm within a scenario only. Four repeats do not establish equivalence or provide reliable inference for modest effects. Report all regimes and failures. The no-cost control diagnoses mechanisms; it does not claim real mating has no cost. Initial program labels remain fixed and permanent losses are absorbing without immigration or modifier-mediated strategy transitions.

## Planning 100 million years

`plan-time` performs arithmetic only and never invokes the simulation. A caller must supply `--years-per-step`; this is an explicitly unvalidated calendar mapping. For overlapping cohorts, a census update is not a genetic generation. Mapping a step to 1,000 years does not simulate the reproduction, mortality, mutations, environmental transitions and catastrophes that would happen during those years. All rates and age thresholds need joint calibration to a named organism/time unit and timestep convergence.

At an assumed one year per step, 100 million years at capacity 336 requires up to 33.6 billion individual updates per run. With 16 loci and eight repeats this is 4.3008 trillion individual-locus updates. The precomputed target alone would require 1,600,000,016 bytes per run, the Boolean onset schedule another 100,000,000 bytes, and a full horizon retains 800,000,000 population/resource ledger rows before metrics, genomes and lineage. These are structural counts, not measured process memory or proof that a run is feasible.

The planner reports all exceeded existing workload guards. Optional runtime numbers are explicitly naive linear kernel extrapolations from complete matching-mechanism benchmarks with the same source/runtime signature. They exclude long-history memory/I/O effects, are neither bounds nor reliable deep-time forecasts, and do not override guards. Early-extinction benchmark timings are rejected for full-horizon extrapolation. No 100-million-year run is started by planning or by this pilot.

## Further development gates

1. Calibrate a named species/life cycle, rate units and meaningful effect sizes. Sensitivity-test focal versus nonfocal genetic selection, hard donor/gamete budgets and Mendelian reproductive modifiers; hold catastrophe controls fixed while testing those changes.
2. Add multiple habitat patches, partial/local catastrophes, refuges and migration with explicit conservation and dispersal costs. Separate shared versus spatially correlated shocks and test rescue after local extinction. Primary models of local catastrophes/dispersal motivate this question, but their parameter values are not adopted as calibration: [Gyllenberg et al. (2002)](https://pubmed.ncbi.nlm.nih.gov/12181600/).
3. Add independently reproducing pathogens and explicit heritable resistance/environmental traits if those mechanisms are part of the claim. Do not call the existing bit-vector tracker a calibrated epidemic.
4. Profile population, genome and horizon scaling separately, including peak process memory and checkpoint growth. Stream or compact histories; validate an approximate/count-based or compiled engine against exact small-population references before deep-time use. Genotype counts must preserve the associations, ages and spatial structure needed for the target question.
5. Evaluate SLiM/tree-sequence methods for realistic nuclear genomes and compact ancestry. Tree-sequence recording can defer neutral mutation placement and compact genealogies; it does not automatically permit skipping selected ecological dynamics or establish realistic geological scenarios. [Haller et al. (2019)](https://pubmed.ncbi.nlm.nih.gov/30565882/) is a primary demonstration of these methods, not a benchmark for this Python engine or a promised acceleration factor.
6. Freeze independent confirmatory seeds, held-out environments, statistical families, thresholds and power/precision before larger inference. Long duration and more repetitions answer different questions. Over deep time in a finite closed patch, early fixation/extinction can leave no strategies to compare; speciation, macroevolution and historical feasibility are not implemented by extending the clock.

All generated pilot results, performance reports and research interpretation remain local under ignored `runs/` and `reports/`. A stronger scenario is one whose assumptions are justified and tested, rather than one that selects a desired winner.
