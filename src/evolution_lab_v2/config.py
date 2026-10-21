"""Strict, bounded JSON configuration for reference experiments."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Config:
    reproduction: str = "clone"
    population_size: int = 200
    generations: int = 50
    chromosome_lengths: tuple[int, ...] = (8, 8)
    seed: int = 2026
    initial_frequency: float = .5
    mutation_rate: float = 0.0
    recombination_rate: float = .01
    selection_coefficient: float = 0.0
    dominance: float = .5
    log_every: int = 1
    checkpoint_every: int = 10

    def __post_init__(self):
        for name in ("population_size", "generations", "seed", "log_every", "checkpoint_every"):
            value = getattr(self, name)
            minimum = 0 if name in ("generations", "seed") else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.reproduction not in ("clone", "two_parent"):
            raise ValueError("Gate 2 supports clone and two_parent only")
        if self.reproduction == "two_parent" and self.population_size < 2:
            raise ValueError("two_parent requires at least two distinct adults")
        if not isinstance(self.chromosome_lengths, (tuple, list)) or not self.chromosome_lengths:
            raise ValueError("chromosome_lengths must be a nonempty sequence")
        if any(type(x) is not int or x < 1 for x in self.chromosome_lengths):
            raise ValueError("chromosome lengths must be positive integers")
        object.__setattr__(self, "chromosome_lengths", tuple(self.chromosome_lengths))
        for name in ("initial_frequency", "mutation_rate", "recombination_rate",
                     "selection_coefficient", "dominance"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability")
        if self.recombination_rate > .5 or self.selection_coefficient >= 1:
            raise ValueError("recombination_rate must be <= .5; selection_coefficient must be < 1")
        if self.population_size > 10000 or self.loci > 4096:
            raise ValueError("Pilot limits: population <= 10000 and loci <= 4096")
        if self.population_size * self.generations > 1_000_000:
            raise ValueError("Pilot limit: at most 1,000,000 individual generations")
        if self.population_size * max(1, self.generations) * self.loci > 50_000_000:
            raise ValueError("Pilot limit: at most 50,000,000 individual-locus generations")

    @property
    def loci(self):
        return sum(self.chromosome_lengths)

    def to_dict(self):
        result = asdict(self)
        result["chromosome_lengths"] = list(self.chromosome_lengths)
        return result

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError(f"Invalid configuration: {exc}") from exc

    @classmethod
    def read(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
