"""Explicit, bounded demographic experiment parameters; no empirical calibration."""
from dataclasses import asdict, dataclass
import math

STRATEGIES = ("clone", "two_parent", "facultative", "periodic", "stress", "four_parent", "eight_parent")
PARENTS = (1, 2, 2, 2, 2, 4, 8)
MAX_RUN_CENSUS_TICKS = 2_000_000
MAX_RUN_LOCUS_TICKS = 50_000_000
MAX_BATCH_CENSUS_TICKS = 50_000_000
MAX_BATCH_LOCUS_TICKS = 1_000_000_000


@dataclass(frozen=True)
class EcoConfig:
    model: str = "demographic"
    seed: int = 20261020
    steps: int = 100
    initial_counts: tuple[int, ...] = (32, 32, 32, 32, 32, 32, 32)
    capacity: int = 336
    chromosome_lengths: tuple[int, ...] = (4, 4, 4, 4)
    initial_frequency: float = .5
    maturity_age: int = 2
    max_age: int = 16
    senescence_age: int = 8
    senescence_rate: float = .06
    survival_probability: float = .85
    fecundity: float = .65
    selection_coefficient: float = .04
    dominance: float = .5
    mutation_rate: float = .001
    recombination_rate: float = .05
    mating_cost: float = 0.0
    extra_parent_cost: float = 0.0
    encounter_probability: float = 1.0
    compatibility_scope: str = "within_strategy"
    compatibility_matrix: tuple[tuple[bool, ...], ...] = ((True, True), (True, True))
    multiparent_mechanism: str = "locus_mosaic"
    facultative_probability: float = .1
    modifier_mutation_rate: float = .001
    modifier_step: float = .05
    period: int = 10
    stress_threshold: float = .75
    facultative_fallback: bool = True
    environment: str = "static"
    environment_period: int = 20
    environment_flip_rate: float = .03
    seasonal_amplitude: float = .25
    parasite: str = "none"
    parasite_strength: float = .15
    parasite_period: int = 5
    parasite_noise: float = .05
    resource_capacity: float = 600.0
    initial_resources: float = 600.0
    resource_renewal: float = 150.0
    maintenance_cost: float = .25
    offspring_resource_cost: float = 1.0
    log_every: int = 5
    checkpoint_every: int = 25
    establishment_size: int = 48
    record_parentage: bool = True
    max_logged_births: int = 100000
    catastrophe_regime: str = "none"
    catastrophe_probability: float = 0.0
    catastrophe_mortality: float = .5
    catastrophe_resource_loss: float = .75
    catastrophe_renewal_factor: float = .25
    catastrophe_duration: int = 8

    def __post_init__(self):
        if self.model != "demographic":
            raise ValueError("Expected demographic model")
        for name in ("seed", "steps", "capacity", "maturity_age", "max_age", "senescence_age",
                     "period", "environment_period", "parasite_period", "log_every", "checkpoint_every",
                     "establishment_size", "max_logged_births", "catastrophe_duration"):
            minimum = 0 if name in ("seed", "steps", "maturity_age", "senescence_age") else 1
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        for name in ("initial_counts", "chromosome_lengths"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or not value:
                raise ValueError(f"{name} must be a nonempty list")
            minimum = 0 if name == "initial_counts" else 1
            if any(type(x) is not int or x < minimum for x in value):
                raise ValueError(f"Invalid {name}")
            object.__setattr__(self, name, tuple(value))
        if len(self.initial_counts) != len(STRATEGIES) or not 0 < sum(self.initial_counts) <= self.capacity:
            raise ValueError("initial_counts must specify seven nonnegative counts with total 1..capacity")
        if 2*self.loci < max(PARENTS[s] for s, count in enumerate(self.initial_counts) if count):
            raise ValueError("Too few allele-copy positions for every required genetic parent to contribute")
        if not self.maturity_age <= self.senescence_age < self.max_age:
            raise ValueError("Require maturity_age <= senescence_age < max_age")
        probabilities = ("initial_frequency", "survival_probability", "selection_coefficient", "dominance",
                         "mutation_rate", "recombination_rate", "encounter_probability", "facultative_probability",
                         "modifier_mutation_rate", "modifier_step", "stress_threshold", "environment_flip_rate",
                         "seasonal_amplitude", "parasite_strength", "parasite_noise",
                         "catastrophe_probability", "catastrophe_mortality",
                         "catastrophe_resource_loss", "catastrophe_renewal_factor")
        for name in probabilities:
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability")
        if self.selection_coefficient >= 1 or self.recombination_rate > .5 or self.seasonal_amplitude >= 1:
            raise ValueError("Require selection < 1, recombination <= .5 and seasonal_amplitude < 1")
        for name in ("senescence_rate", "fecundity", "mating_cost", "extra_parent_cost", "resource_capacity",
                     "initial_resources", "resource_renewal", "maintenance_cost", "offspring_resource_cost"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.resource_capacity <= 0 or self.offspring_resource_cost <= 0 or self.initial_resources > self.resource_capacity:
            raise ValueError("Resource capacity/offspring cost must be positive; initial resources <= capacity")
        if self.fecundity > 4 or self.capacity > 5000 or self.loci > 256:
            raise ValueError("Demographic pilot limits: fecundity <= 4, capacity <= 5000, loci <= 256")
        if self.capacity * self.steps > MAX_RUN_CENSUS_TICKS or self.capacity * max(1, self.steps) * self.loci > MAX_RUN_LOCUS_TICKS:
            raise ValueError("Demographic pilot workload exceeds individual/locus update limits")
        if self.max_logged_births > 250000:
            raise ValueError("max_logged_births must be <= 250000")
        if self.compatibility_scope not in ("within_strategy", "all_mixing"):
            raise ValueError("compatibility_scope must be within_strategy or all_mixing")
        matrix = self.compatibility_matrix
        if not isinstance(matrix, (list, tuple)) or not 1 <= len(matrix) <= 8:
            raise ValueError("Provide a compatibility matrix with 1..8 mating types")
        if any(not isinstance(row, (list, tuple)) or len(row) != len(matrix) or
               any(type(v) is not bool for v in row) for row in matrix):
            raise ValueError("Compatibility matrix must be square and boolean")
        if any(matrix[i][j] != matrix[j][i] for i in range(len(matrix)) for j in range(len(matrix))):
            raise ValueError("Pairwise compatibility must be symmetric")
        object.__setattr__(self, "compatibility_matrix", tuple(tuple(row) for row in matrix))
        if self.multiparent_mechanism not in ("locus_mosaic", "chromosome_partition"):
            raise ValueError("Unknown hypothetical multiparent mechanism")
        if self.multiparent_mechanism == "chromosome_partition":
            if 2 * len(self.chromosome_lengths) % 8 or len(set(self.chromosome_lengths)) != 1:
                raise ValueError("chromosome_partition requires equal chromosome lengths and chromosome count divisible by four")
        if self.environment not in ("static", "periodic", "autocorrelated") or self.parasite not in ("none", "fixed", "tracking"):
            raise ValueError("Unsupported environment or parasite regime")
        if not isinstance(self.catastrophe_regime, str) or self.catastrophe_regime not in ("none", "bottleneck", "drought", "combined"):
            raise ValueError("Unsupported catastrophe regime")
        for name in ("record_parentage", "facultative_fallback"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

    @property
    def loci(self):
        return sum(self.chromosome_lengths)

    def to_dict(self):
        result = asdict(self)
        for name in ("initial_counts", "chromosome_lengths"):
            result[name] = list(result[name])
        result["compatibility_matrix"] = [list(row) for row in self.compatibility_matrix]
        return result

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Demographic config must be an object")
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError(f"Invalid demographic config: {exc}") from exc
