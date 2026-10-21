# Demographic model v0.2: explicit assumptions

This is an individual-based diploid toy model with overlapping cohorts. Its scientific value is transparent, tested accounting and falsifiable sensitivity comparisons. It is not calibrated to an organism. The separate fixed-census reference and its neutral equations remain described in `MODEL_ASSUMPTIONS.md`; they are not replaced by this engine.

## State and order of events

Persistent integer IDs identify individuals; birth step determines age. Each has a phased diploid binary genome, a reproductive-program label, a mating type, and a facultative mixing-bout probability. Initial program counts are allocated with wide integers. Founder genomes are independent Bernoulli(.5); initial ages are uniform from 0 through min(max_age-1, maturity_age+3). These demographic initializations are assumptions, not a stable-age-distribution claim.

At step t, events occur in this declared order:

1. When applicable, the parasite updates toward common immunity alleles, with independent noise.
2. Baseline stochastic survival and age-dependent senescence operate identically across programs; individuals at/above max_age die before breeding.
3. The shared resource pool renews up to its ceiling. If maintenance cannot be paid for everyone, a uniform lottery selects who is maintained. Deaths are recorded separately.
4. All surviving individuals of age >=maturity_age are eligible. Breeders from any birth cohort may mate. Reproductive opportunities depend on the same fecundity/score/declared-effort equation.
5. Eligible, distinct, pairwise compatible nuclear parents are selected. Mating and encounter failures and optional facultative fallback are recorded.
6. Candidate diploid offspring inherit nuclear genomes and then mutate. The focal breeder transmits program label and quantitative modifier; mating type is inherited from a uniformly selected contributor (from the focal breeder for clones). These traits are bookkeeping outside the selected nuclear loci and are not claimed to obey a specified nuclear modifier locus.
7. A uniform lottery among all candidate offspring allocates limited construction resources. A second, shared uniform lottery among surviving adults and funded offspring enforces the declared census ceiling. There is no forced restoration.
8. Accepted newborns receive birth step t+1. Census and events are recorded at t+1. Parents' eligibility is checked at the recorded mating step t; newborns cannot breed in their birth step unless maturity=0 explicitly permits it at the next update.

Resources satisfy `after = before + renewal - overflow - maintenance - offspring_construction`. Each strategy satisfies `end = start - survival_deaths - maintenance_deaths - capacity_adult_deaths + recruited_newborns`. Raw candidate, funded, resource-rejected, capacity-killed and recruited newborn counts are separate. Both conservation equations are checked every step. Resource used on a funded offspring later killed by capacity is spent and not refunded. Raw candidate IDs never become reused IDs, including rejected candidates.

## Fitness, environments and parasite assumptions

The environmental target is a binary vector. A diploid locus with zero/one/two mismatching copies contributes 1 / (1-hs) / (1-s) to a multiplicative performance score. This symmetrical treatment of target flips and dominance is a chosen genetic model. Performance modifies expected focal reproductive effort; stochastic age survival and uniform resource/census regulation do not also apply hidden genetic selection.

Static environments retain the target. Periodic environments flip it every configured period. Autocorrelated environments independently flip each locus with configured per-step probability. Nonstatic regimes also impose sinusoidal resource renewal with declared amplitude/period. Selection and resource seasonality therefore co-vary by design; individual causal contributions require additional factorial controls. No temperature, generation-time or physical resource calibration is implied.

Parasites can be absent, fixed, or a noisy bit-vector tracker of common alleles in the last quarter of the genome. Matching that vector multiplies performance by exp(-strength × matching_fraction). This is a synthetic frequency-dependent selection pressure, not an independently evolving pathogen population, measured infection process or calibrated coevolution. The environmental target also acts at these loci, so both pressures may interact.

`adaptive_lag` is mean absolute mismatch between diploid allele dosage/2 and environmental target, not a measured phenotypic lag. `mean_linked_D2` is mean squared gametic D over adjacent loci within chromosomes, using phased homologs; chromosome boundaries are excluded. Heterozygosity and mean[2p(1-p)] are distinguished. Mean performance is not reproductive-value-weighted lifetime fitness. No single score determines a universal winner.

## Programs, compatibility and cost units

Clone copies both homologs. Two-parent reproduction always requires two distinct adults. Facultative reproduction chooses a sexual bout with its inherited probability per mature individual per step; all opportunities of that individual in that step share that intended mode. Periodic mixing occurs at step 0 and multiples of the configured period. Stress mixing occurs individually when performance is below the threshold. Four/eight programs always require four/eight contributors. All facultative modes explicitly allow clonal fallback by default when a sexual search fails; the intended sexual effort remains charged. Obligates never silently fall back.

Mating types are categorical compatibility states and do not determine required parent count. The symmetric Boolean matrix is checked pairwise among all group members. `within_strategy` adds reproductive isolation by program; `all_mixing` allows contributors from any mixing-capable program. Permanent clones cannot donate to sexual groups. No birth-cohort filter exists. General compatibility uses sequential random feasible mates; a greedy path may fail despite another valid group existing. That is a stated encounter process, not an exhaustive matching algorithm. Conditional on sufficient breeders, completing k-1 encounters has probability encounter_probability^(k-1).

For intended k contributors, effort c=1 for clones, or `1 + mating_cost + extra_parent_cost*(k-1)` for mixing. Focal opportunities are Poisson(fecundity × performance / c). Hence expected nominal effort per eligible focal breeder is fecundity × performance for every program. This matches **expected focal effort**, not a hard per-person energy budget. A failed attempt consumes its declared effort. Construction food is charged once for each funded offspring; mating effort is a different unit and is not also subtracted as food.

Donor participation is reusable without an individual donor debit or limit. `extra_parent_cost` is an explicit focal proxy for contribution effort; it is not proof of matched hard energetic budgets or biological gamete production. The zero-cost cases are deliberately idealized. This assumption must remain visible when interpreting multiparent performance. There are no males, females, sex ratios or twofold cost-of-males claim.

## Nuclear inheritance and hypothetical systems

Two-parent offspring receive one recombinant haploid gamete per parent. Chromosomes assort independently and adjacent homolog switches follow r, as in the validated reference. Diploid size and construction food stay the same across all programs.

For four/eight contributors, each selected adult makes one haploid gamete. Two separately named inventions are compared:

- **Coverage-constrained locus mosaic:** choose donor independently for every output allele copy, then reserve one uniformly positioned distinct copy for each donor by overwriting those slots. Remaining slots retain their uniform draws. This guarantees every required parent actually transmits at least one allele copy. It is an explicit coverage-constrained distribution, not unconstrained independent mixing or uniform sampling conditional on coverage, and it breaks linkage between donor choices.
- **Balanced chromosome partition:** pool k haploid gametes and form a diploid output by assigning each intact chromosome copy to a donor using a random donor order and cycling through donor pairs per chromosome. Chromosomes have equal lengths and their count is divisible by four. Each contributor supplies exactly 2L/k allele copies. This enforces whole-chromosome transfer, balanced contribution and diploid dosage. The required fusion/reduction machinery is invented; these bookkeeping constraints do not establish biological feasibility or a historical example. The discarded gamete material is not physically tracked as nutrient loss; contribution effort is only the declared proxy above.

At least 2L>=k allele-copy slots are required. Every selected nuclear parent has positive realized contribution; all children have exactly two homologs and 2L copies. Mutation occurs after inheritance. Both selected-parent slots and positive-contributor slots are counted and lineage rows retain the exact contribution per parent. The baseline's unconstrained mosaic remains unchanged and is not relabeled as validated meiosis.

## Scope and validation limits

Ledger identities, neutral analytical checks in the reference, unbiased opportunity controls, inheritance, mating eligibility and replay are tested. Empirical realism, long-horizon convergence, spatial migration, independently evolving pathogens, true Mendelian reproductive modifiers, hard donor budgets, origin paths to four/eight reproduction and validation against an independent simulator remain open.

The distinction between analytical references and ecological life cycles is motivated by [Haller and Messer (2019), SLiM 3](https://doi.org/10.1093/molbev/msy228). Species-calibrated model catalogs such as [Adrion et al. (2020), stdpopsim](https://doi.org/10.7554/eLife.54967) motivate later calibration/provenance work; their measurements are not used to justify these synthetic parameter values.
