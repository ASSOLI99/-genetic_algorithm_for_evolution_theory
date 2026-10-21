# V2 fixed-census reference assumptions — introduced in version 0.1.0

Scope: the preserved mathematical reference only. The separate v0.2 demographic model is specified in `ECO_MODEL.md`; its readiness protocol is `ECO_PROTOCOL.md`. Do not apply the fixed-census life cycle below to demographic outputs.

This milestone implements a diploid population-genetics reference with clone and obligate two-parent reproduction. It is a mathematical control, not a reconstruction of any species. No parameter in the provided toy configurations is claimed to be empirically calibrated. Biological realism is limited to explicit phased inheritance, chromosome assortment, linkage and a simple dominance model.

## Life cycle

The initial census is N diploid individuals with two phased homologs at each binary locus. Founder alleles are independent Bernoulli(p0). Separate clone/two-parent runs with identical seed and genome configuration have identical founders.

For each update, all current adults are eligible and exactly N offspring replace the adults. There is no selfing in two-parent mode: ordered parents are sampled sequentially, proportional to their remaining weights, without replacement within each offspring. Reuse across offspring is allowed. This excludes selfing and is therefore a modified diploid Wright–Fisher reference, not the exact independent-gamete WF model. Generations do not overlap in this reference; it cannot test cross-cohort breeding. The subsequent demographic engine must allow all living, mature, compatible cohorts.

For locus dosage d, the relative fecundity factor is 1 (d=0), 1-hs (d=1), or 1-s (d=2), multiplied across loci. Log weights avoid underflow during normalization. There is no survival selection in this reference. `mean_viability_score` reports the mean of that multiplicative score, not observed lifetime reproductive success. If s=0, allele 1 has no intrinsic adverse meaning. h and s are sensitivity parameters; the default is neutral.

Clones copy both parental homologs, preserving phase. A two-parent child receives one haploid gamete from each distinct parent. Each chromosome starts on a uniformly chosen homolog; adjacent loci switch homolog with probability r. Chromosomes assort independently. This is a discrete recombination map; crossover interference, gene conversion, structural variation and explicit physical lengths are omitted. r=0 means complete linkage within each chromosome, not between chromosomes. All allele copies flip symmetrically 0↔1 with independent probability mu after inheritance. There are no strategy mutations or modifier alleles yet.

## Costs and symmetry

Both modes receive exactly N offspring slots and have zero encounter, mating, gamete and allocation costs. This is an idealized equal-output/no-cost control, not a measured equal-energy budget. There is no twofold-cost-of-males assumption and there are no sexes or mating types. Fixed census is declared explicitly: resource-limited growth, extinction and invasion are not estimable. Future demographic work must support zero-cost and matched nonzero budgets with births, deaths, attempted offspring, resource use and culling separately recorded. It must not restore census when reproduction fails.

Expected neutral allele frequency is conserved for both modes. Drift variance need not match. Conditional on fixed founders with diploid allele fraction q_i, p=mean(q_i), and Vq=mean((q_i-p)^2), one-step variance of offspring allele frequency is:

- Clone: Vq/N.
- Two distinct uniform parents: [p(1-p) - Vq/(N-1)]/(2N).

For two parents, each sampled gamete is marginally Bernoulli(p), and the two gametes have covariance -Vq/(N-1) because the two sampled adult identities differ. Different offspring are independent conditional on founders. The tests use balanced 0/0 and 1/1 founders to compare both conditional mean and variance to these equations. They do not falsely require equal drift or impose the selfing-allowed WF variance p(1-p)/(2N).

## Recorded quantities and reproducibility

Every retained metric contains population size, mean allele frequency, per-locus allele frequencies, gene diversity mean[2p(1-p)], observed heterozygosity, allele-1 copy count, mean score, and realized offspring/adult deaths for that update. Birth/death values are per-update, not cumulative between sampled rows. Generation 0 has no births/deaths. Each offspring's full parent identities are recorded with generation-qualified indexes; these identify selected nuclear parents, not necessarily ancestors at every locus. Exact crossover breakpoints and mutation events are not retained.

PCG64 is explicit. Configurations, seeds, Python/NumPy/package versions, source and protocol hashes, Git SHA and dirty status are recorded. Checkpoints include all genomes, ancestry, RNG state, prior sampled metrics and configuration; loading uses `allow_pickle=False` and rejects mismatched code/runtime/config. Same-environment replay is tested, including checkpoints outside metric sampling times. Cross-platform stream identity is not promised; NumPy documents the strict conditions for [stream compatibility](https://numpy.org/doc/stable/reference/random/compatibility.html).

## Scientific references

[Adrion et al. (2020), eLife 9:e54967](https://doi.org/10.7554/eLife.54967) describes community-standard simulation models and empirical parameter catalogs. It motivates documented model provenance; it does not calibrate this toy configuration.

[Haller and Messer (2019), Molecular Biology and Evolution 36:632–637](https://doi.org/10.1093/molbev/msy228) distinguishes Wright–Fisher references from nonWF models supporting age structure and ecological demography. It motivates the separate engines; it is not evidence for a reproductive winner here.

The conditional variance equations above are derived for this implementation's assumptions. Later empirical parameter ranges must be tied to a named organism, trait, unit and primary measurement; generic cross-species numbers will not be presented as calibration.
