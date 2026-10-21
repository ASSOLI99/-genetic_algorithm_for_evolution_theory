# Experimental protocol — 2026-10-20

Protocol version 0.1.0, specified before V2 pilot results. Purpose: validate E0/E1 and estimate implementation costs. The supplied baseline CSV was already observed and is retrospective evidence only. No confirmatory biological inference is preregistered by this local document.

## Current milestone: E0 and E1

E0 preserves original files and hashes, runs original tests, audits all CSV records and seeds, and checks deterministic reproduction. Report all defects without changing the historical reference.

E1 uses the two neutral JSON configurations (N=200, 50 generations, two chromosomes of eight loci, p0=.5, s=0, mu=0). The demonstration grid crosses reproduction [clone, two_parent] and recombination rate [0, .1], four replicates per cell, master seed 20261020. Clone recombination rate is an inactive control; these two clone configurations are duplicates in mechanism and are never pooled as independent observations. Founders are paired within replicate by spawned SeedSequence seeds; after initialization the RNG consumption differs between mechanisms. This is founder pairing, not a claim of common random environmental histories. No environments exist in E1.

The pilot primary diagnostic is final gene diversity. Neutral expected allele-frequency conservation and model-specific one-step variance are validation targets. Heterozygosity, copy count and mean score are secondary diagnostics. Finite populations have drift even without selection; different recombination/inheritance mechanisms need not have equal drift. There is no winner label or performance ranking from diversity alone.

Tests use 1,200 independent fixed-seed one-generation replicates per mechanism at N=40 and one locus with balanced homozygous founders. Mean deviation must be within six Monte Carlo standard errors; empirical variance must be within 20% of the derived expectation. These are numerical sanity tolerances, not significance thresholds for biological comparisons. Property-based parent-sampling tests use deterministic generation, 60 cases, sizes 8..80 and requested group sizes 1/2/4/8.

Sweeps write their full planned run/config/seed manifest before simulation. Analysis consumes exactly those listed summaries; incomplete/mismatched runs must be treated as failures, not silently omitted. The report gives replicate means, sample SD and descriptive percentile bootstrap 95% intervals with 2,000 resamples and separate PCG64 seed 73021. n=1 has no interval. Paired contrasts are two-parent minus clone within the same seed and every other shared configuration. Four replicates are a software demonstration, insufficient for precise scientific inference. CIs are unadjusted and exploratory; no hypothesis-test declarations or multiple-comparison claims are made.

## Later experiments and gates

Before E2–E6, freeze a separately versioned protocol with evidence-backed parameter ranges or explicit speculative labels, smallest meaningful effect sizes, exclusion/failure rules, primary endpoint families, resource definitions, held-out environments, precision targets and power estimates from pilots.

| Experiment | Design requirement | Endpoints and inference |
|---|---|---|
| E2 established competition | Adequate initial abundance; shared and separate patches; costs 0/low/medium/high; at least 3 environmental and 3 parasite regimes; population-scale convergence. Hold explicit life-history budgets constant. | Extinction probability by 10,000 updates, survival curves with exact extinction events and censoring, population shares, log relative growth. Do not equate score with persistence. |
| E3 modifiers/invasion | Rare defined modifier; separate mutation supply and compatibility origin from post-introduction selection. Include coordinated compatible introductions and resident controls. | Establishment probability with denominator of actual introductions, fixation conditional on compatibility, time to threshold. Predefine threshold and detection window. |
| E4 facultative | Evolvable exchange probability/trigger; periodic, stress, never and always controls. Explicit behavior when compatible mates are absent. | Same primary demographic endpoints; modifiers and exchange frequency secondary. |
| E5 hypothetical 4/8 | Separate locus-mosaic mechanism and a physically constrained gamete/ploidy hypothesis, with explicit ancestry fractions, dosage and maintenance costs. Vary compatibility independently of required contributor count. | Scenario-specific effects under both idealized free and encounter-limited contribution; no claim of historical occurrence. |
| E6 held-out validation | Hold out parameter configurations before fitting/optimization; compare reference cases against an independent simulator and empirical data where appropriate. | Generalization, calibration errors and failure cases, not a universal optimum. |

For confirmatory contrasts, use independent replicate blocks, report paired effects where valid and all uncertainty. Choose a correction such as Holm within a preregistered primary contrast family before seeing outcomes; descriptive intervals must not become significance claims. Use a separately recorded analysis/bootstrap seed. Report zero denominators, extinct populations, missing and failed runs. Reserve environmental RNG streams separately before ecological comparisons. Replicate seed reuse across mechanisms is a pairing device; it does not create extra independent samples.

## Computation and stopping

Current guards: census <=10,000, <=1,000,000 individual generations per run, <=50,000,000 individual-locus generations per run, <=128 sweep runs and <=100,000,000 individual-locus generations per sweep. These are conservative engineering limits, not biological assumptions. Benchmarks are capped separately. Current pilot uses N<=1,000 for measured benchmarks and N=200 for sweeps. No million-individual experiment is launched.

Benchmark initialization/kernel/metric/ancestry cost separately from disk/checkpoint cost, report repeats and environment. The finite weighted sampler currently scales O(N²) per generation; optimizing it requires preserving conditional sampling tests and replay expectations. Log actual memory and runtime before changing caps. A million × 10,000 × 100 target implies 10^12 individual generations before genome/parent work, and is not authorized by passing a small reference test. Profile, estimate, design checkpoints, choose approximations explicitly, and obtain consent for expensive work.
