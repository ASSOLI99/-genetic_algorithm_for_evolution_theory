# Demographic comparison protocol v0.2 — 2026-10-20

This protocol is specified before running the readiness pilot or the main comparison. It extends the retrospective E0 audit and analytical E1 checks; neither constitutes empirical validation of ecology. Parameters are synthetic, not estimates for a species. Results are falsifiable comparisons of these stated mechanisms, not a universal ranking or a reconstruction of the origin of sex.

## Ready experiment

`configs/comparison_ready.json` defines 144 scenarios, eight independent replicate blocks per scenario, master seed 20261020, 80 **census steps**, initial census 224 (32 per strategy), capacity 336 and four chromosomes of four binary loci. These are overlapping demographic steps, not 80 genetic generations. The full cross is:

- Mating initiation cost: 0 or .2.
- Additional contributor effort: 0 or .04 per additional parent.
- Environment: static, periodic, or binary autocorrelated.
- Parasite: none, fixed, or host-frequency tracking.
- Hypothetical 4/8 mechanism: coverage-constrained locus mosaic or balanced intact-chromosome partition.
- Compatibility scope: within reproductive program, or between all mixing-capable programs. Permanent clones cannot donate to sexual groups in either scope.

Thus zero-cost, mating-only, contributor-only and combined-cost cases are all included. Resource renewal, initial resources, maintenance, base fecundity, mortality, maturity, senescence, offspring resource price and census culling rule are common to strategies. No extra mortality or fecundity multiplier is silently applied by reproductive program. Intended mating size affects only the declared effort/encounter/compatibility and inheritance rules. All configuration defaults are expanded into the planned per-run manifest before any results.

The primary endpoint is strategy census at the fixed horizon, including zero for extinction. Secondary endpoints are extinction probability, exact discrete census-loss times, population shares conditional on nonempty total population, survival-conditioned log growth, offspring per construction resource, mean performance, diversity, heterozygosity, linked D², adaptive lag, mate/encounter failures, realized offspring and facultative trait distribution. Report the denominator and conditioning; a population-wide extinction has undefined shares, not seven artificial zero shares or a winner.

There is no promise of adequate power with eight replicates. This is the first exploratory comparison. A threshold for practically meaningful effects and precision/power calculations must be added before confirmatory biological claims or longer powered runs. Eight replicates can reveal large scenario-specific differences while leaving substantial uncertainty. No result is excluded for extinction or an unfavorable outcome. Failed runs make the batch incomplete; automatic analysis must reject them.

## Controls and introduction experiment

`configs/comparison_isolated.json` supplies 42 scenarios × eight replicates: each program alone at the same total initial census (224), crossed with three environments and two multiparent mechanisms. Resource supply and founder genotype/age/type generation are common. These separate the seven-way competition question from isolated persistence. This file is a separate run, not pooled with competition or treated as extra independent replicates. Recombination mechanism is inactive for clone/two-parent programs and must not be counted as replication.

`configs/invasion_facultative.json` supplies four scenarios × sixteen replicates, master seed 908102026, 200 steps. Eight facultative individuals are introduced alongside 216 clones at time zero, with a declared mix probability .1 and the usual compatible-type assumptions. The primary endpoint is the probability of reaching 48 individuals at least once by the horizon, conditional on that designed introduction. Report the actual introduction denominator, threshold times, fixation probability and cases crossing the threshold and subsequently going extinct. Reaching 48 does not imply fixation or persistent establishment. This does not model the evolutionary origin of an entire mating program or the transition from two to four/eight parents. Raw final-count tests against a numerically larger resident are suppressed.

The facultative mix-bout probability is inherited from the focal breeder and can mutate by a small Gaussian step with reflecting [0,1] bounds. This is a hypothetical separately inherited quantitative modifier, not a located Mendelian locus. E3 concerns this defined introduction; no direct one-step mutation invents a 4/8-parent program.

## Stochastic design and inference

Each replicate seed is spawned from SeedSequence(master_seed). Within a replicate, eight PCG64 streams separate exogenous environment, founders, mortality, mating, nuclear inheritance, resource lotteries, parasite dynamics and modifier mutation. Same-parameter founders and exogenous environments are paired across cost/compatibility/mechanism scenarios. Mortality/mating streams can diverge as census changes; we do not claim full common-random-number trajectories. Tracking parasites are endogenous, so shared noise does not imply identical pathogen histories.

Analysis uses every planned run and exactly the planned replicate seeds. It validates configurations, source/runtime signatures and output digests. Mean abundance and paired final-count differences have descriptive percentile bootstrap 95% intervals (2,000 resamples, independent analysis seed 73021). Extinction and introduction proportions have Wilson 95% intervals. n=1 has no bootstrap interval. Intervals are not familywise simultaneous confidence statements.

For equal initial-abundance strategies, a paired exact sign test compares each program with clone using final count differences across replicate blocks, discarding ties but reporting them. Its null is equal probability of positive and negative nonzero differences, not equality of means. Holm adjusts the six contrasts within each scenario; it does not correct the exploratory grid across scenarios. No automatic significance/winner classifier is produced. Unequal initial abundances in introduction/isolated experiments are not passed through those equal-start count contrasts.

Survival curves use exact integer census times of first zero and right censor surviving strategies at the configured horizon. Labels cannot mutate or migrate in this engine, so absence is absorbing. Initially absent strategies are outside the extinction risk set. A global extinction can terminate a run early because all later counts are exactly zero. Within-step event times are not continuous-time observations.

Figures are deterministic choices from the plan: mean-final-abundance heatmaps for all scenarios and abundance/survival trajectories for the first and last planned scenario, not selected by favorable outcomes. Counts and uncertainty for every scenario remain in CSV/JSON. PNG/SVG plots use Matplotlib; [its export interface](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html) supports both formats.

## Readiness gate and computation

`configs/comparison_smoke.json` is a distinct eight-run pilot (four mechanism/scope cells × two seeds; master seed 89102026; 30 steps). It exercises autocorrelated environments, tracking parasites, nonzero costs, logs, reports and checkpointing. Its results are software evidence only and are never pooled into the main seed schedule. Unit/statistical tests cover analytical neutral inheritance, zero-cost opportunity symmetry, eligibility, contribution accounting, resource and population conservation, exact extinction, mismatch/corruption detection and exact replay outside metric logging times.

No main comparison is run merely to declare the software ready. The user launches it after the completed smoke gate. The comparison plans at most 30,965,760 capacity-based individual steps / 495,452,160 individual-locus steps. These are workload upper bounds for existing census, not measured operations; candidate generation and logging add work. The runner saves the immutable plan before results, checkpoints at step 40 and the final step, writes progress and supports batch resume with preserved interrupted attempts. It verifies and skips completed runs; altered sources/protocol/runtime/configs cannot resume as equivalent.

Hard guards: capacity <=5,000, loci <=256, fecundity <=4; per run <=2m capacity-steps and <=50m locus-steps; per batch <=256 scenarios/2,048 runs, <=50m capacity-steps and <=1b locus-steps. A Poisson draw above 50,000 attempts in one step or parentage beyond its explicit storage budget raises an error, never clips the biological output. These limits are conservative engineering gates. Main-suite timing/storage estimates must be labeled approximate, based on measured small profiles including logs and checkpoints. No million-individual or trillion-individual-generation experiment is authorized or launched.

Future confirmatory work must vary population scale, horizon, genome length, dominance, initial diversity, mating-type matrices, trigger/encounter parameters and alternative life histories, then hold out environments and compare against an independently implemented simulator/data. Explicit space/migration, species-calibrated ranges, hard donor effort budgets and physically validated multiparent mechanisms remain outside this release.
