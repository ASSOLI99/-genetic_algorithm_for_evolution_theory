"""Versioned, non-pickle checkpoints and source/runtime provenance."""
import csv
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import platform
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

from . import __version__
from .config import Config
from .model import State, observe

ROOT = Path(__file__).resolve().parents[2]


def source_hashes():
    files = sorted(Path(__file__).parent.glob("*.py"))
    files += sorted(p for p in (Path(__file__).parent / "web").glob("*") if p.is_file())
    files += [ROOT / p for p in ("pyproject.toml", "requirements-dev.lock", "MODEL_ASSUMPTIONS.md", "EXPERIMENT_PROTOCOL.md", "ECO_PROTOCOL.md", "ECO_MODEL.md", "DISTURBANCE_PROTOCOL.md", "GUI_PROTOCOL.md") if (ROOT / p).exists()]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def signature():
    dependencies = {}
    for name in ("matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "packaging", "pillow", "pyparsing", "python-dateutil", "six"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    return {"package": __version__, "python": platform.python_version(),
            "numpy": np.__version__, "platform": platform.platform(),
            "dependencies": dependencies, "bit_generator": "PCG64", "source_sha256": source_hashes()}


def provenance():
    def git(*args):
        r = subprocess.run(["git", "-C", str(ROOT), *args], text=True, capture_output=True, check=False)
        return r.stdout.strip() if r.returncode == 0 else None
    return {**signature(), "utc_timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(), "python_executable": sys.executable,
            "git_sha": git("rev-parse", "HEAD"), "git_status": git("status", "--porcelain"),
            "command": sys.argv}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_checkpoint(path, state):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    needed = 1 if state.config.reproduction == "clone" else 2
    ancestry = np.stack(state.parentage) if state.parentage else np.empty((0, state.config.population_size, needed), dtype=np.int64)
    meta = {"schema_version": 1, "signature": signature(), "config": state.config.to_dict(),
            "generation": state.generation, "rng_state": state.rng.bit_generator.state,
            "records": state.records}
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, genomes=state.genomes, parentage=ancestry,
                            metadata=np.array(json.dumps(meta, allow_nan=False)))
    temporary.replace(path)


def load_checkpoint(path, config):
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["metadata"].item()))
        genomes = data["genomes"].copy()
        ancestry = data["parentage"].copy()
    if meta["schema_version"] != 1 or meta["signature"] != signature():
        raise ValueError("Checkpoint code/runtime signature mismatch")
    if Config.from_dict(meta["config"]) != config:
        raise ValueError("Checkpoint configuration mismatch")
    gen = meta["generation"]
    needed = 1 if config.reproduction == "clone" else 2
    if type(gen) is not int or not 0 <= gen <= config.generations:
        raise ValueError("Invalid checkpoint generation")
    if genomes.shape != (config.population_size, 2, config.loci) or genomes.dtype != np.uint8 or (genomes > 1).any():
        raise ValueError("Invalid checkpoint genomes")
    if ancestry.shape != (gen, config.population_size, needed) or ancestry.dtype.kind not in "iu":
        raise ValueError("Invalid checkpoint parentage")
    if (ancestry < 0).any() or (ancestry >= config.population_size).any():
        raise ValueError("Invalid checkpoint parent identifiers")
    if needed == 2 and (ancestry[:, :, 0] == ancestry[:, :, 1]).any():
        raise ValueError("Checkpoint contains selfing")
    records = meta["records"]
    expected_generations = [g for g in range(gen + 1) if g % config.log_every == 0 or g == config.generations]
    if not isinstance(records, list) or [r["generation"] for r in records] != expected_generations:
        raise ValueError("Invalid checkpoint observation schedule")
    rng = np.random.Generator(np.random.PCG64())
    rng.bit_generator.state = meta["rng_state"]
    return State(config, gen, genomes, rng, records, list(ancestry))


def write_outputs(directory, state, manifest):
    directory = Path(directory)
    records = list(state.records)
    if records[-1]["generation"] != state.generation:
        records.append(observe(state))
    with (directory / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    with (directory / "parentage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["offspring_generation", "offspring_index", "parent_generation", "parent_0", "parent_1"])
        for gen, groups in enumerate(state.parentage, 1):
            for child, group in enumerate(groups):
                writer.writerow([gen, child, gen - 1, int(group[0]), int(group[1]) if len(group) == 2 else ""])
    summary = {"schema_version": 1, "config": state.config.to_dict(), "generation": state.generation,
               "complete": state.generation == state.config.generations,
               "model": "fixed_census_diploid_reference", "final": records[-1],
               "genome_sha256": hashlib.sha256(state.genomes.tobytes()).hexdigest(),
               "persistence_estimable": False, "manifest": manifest}
    for filename in ("metrics.csv", "parentage.csv", "checkpoint.npz"):
        manifest.setdefault("artifact_sha256", {})[filename] = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
    write_json(directory / "manifest.json", manifest)
    write_json(directory / "summary.json", summary)
    return summary
