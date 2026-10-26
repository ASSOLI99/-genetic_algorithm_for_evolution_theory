"""Calendar/workload arithmetic only; never launches a simulation."""
import hashlib
import json
import math
from pathlib import Path
import statistics

from .artifacts import signature
from .eco_config import (EcoConfig, MAX_RUN_CENSUS_TICKS, MAX_RUN_LOCUS_TICKS,
                         MAX_BATCH_CENSUS_TICKS, MAX_BATCH_LOCUS_TICKS)


def plan_time(config, years, years_per_step, replicates=1, benchmark=None):
    if not isinstance(config, EcoConfig):
        raise ValueError("Calendar planning requires a demographic config")
    for name, value in (("years", years), ("years_per_step", years_per_step)):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if type(replicates) is not int or not 1 <= replicates <= 32:
        raise ValueError("Require 1..32 replicates")
    ratio = years/years_per_step
    if not math.isfinite(ratio) or ratio > 10**18:
        raise ValueError("Requested planning horizon is too large")
    ticks = max(1, math.ceil(ratio))
    rounded_years = ticks*years_per_step
    if not math.isfinite(rounded_years):
        raise ValueError("Rounded calendar horizon exceeds finite arithmetic")
    census = config.capacity*ticks
    locus = census*config.loci
    exceeded = []
    for label, work, limit in (("run_census_ticks", census, MAX_RUN_CENSUS_TICKS),
                               ("run_locus_ticks", locus, MAX_RUN_LOCUS_TICKS),
                               ("batch_census_ticks", census*replicates, MAX_BATCH_CENSUS_TICKS),
                               ("batch_locus_ticks", locus*replicates, MAX_BATCH_LOCUS_TICKS)):
        if work > limit:
            exceeded.append({"limit": label, "required": work, "maximum": limit})
    report = {"simulation_launched": False, "target_years": years,
              "declared_years_per_step": years_per_step,
              "calendar_mapping": "User assumption, not empirical calibration. Overlapping census steps are not genetic generations.",
              "steps_per_run": ticks, "rounded_calendar_years": rounded_years,
              "replicates": replicates, "capacity": config.capacity, "loci": config.loci,
              "upper_census_ticks_per_run": census, "upper_locus_ticks_per_run": locus,
              "upper_census_ticks_all_runs": census*replicates,
              "upper_locus_ticks_all_runs": locus*replicates,
              "preallocated_environment_bytes_per_run": (ticks+1)*config.loci,
              "preallocated_catastrophe_schedule_bytes_per_run": ticks,
              "retained_accounting_rows_per_run": ticks*8,
              "within_current_workload_guards": not exceeded, "limits_exceeded": exceeded,
              "naive_kernel_extrapolation_seconds_per_run": None,
              "naive_kernel_extrapolation_seconds_all_runs": None,
              "benchmark_candidates": [], "benchmark_rejections": [],
              "limitations": [
                  "Reproduction, mortality, mutation, environment and catastrophe rates require joint calendar calibration.",
                  "Changing years_per_step does not simulate omitted events or recalibrate any biological rate.",
                  "The work counters are capacity-based bounds, not CPU operations or observed generations.",
                  "Memory byte counts cover two arrays only, not genomes, Python ledgers, lineage or process RSS.",
                  "Accounting histories and checkpoints grow with horizon even when parentage recording is disabled.",
                  "Finite isolated populations can lose strategies permanently; no immigration or speciation restores them.",
                  "A short-run linear kernel extrapolation excludes growing-history memory/I/O effects; it is not feasibility verification or a runtime bound."]}
    if benchmark is None:
        return report
    raw = Path(benchmark).read_bytes()
    measured = json.loads(raw.decode("utf-8-sig"))
    report["benchmark_sha256"] = hashlib.sha256(raw).hexdigest()
    recorded = measured.get("provenance", {})
    if any(recorded.get(k) != value for k, value in signature().items()):
        report["benchmark_rejections"].append("Source/runtime signature differs; no timing extrapolation")
        return report
    desired = config.to_dict()
    ignored = {"seed", "steps", "initial_counts", "log_every", "checkpoint_every"}
    for row in measured.get("results", []):
        cfg = row.get("config", {})
        if any(cfg.get(k) != value for k, value in desired.items() if k not in ignored):
            continue
        samples = row.get("measurements", [])
        completed = cfg.get("steps", 0)
        if not samples or completed <= 0 or any(s.get("terminal_tick") != completed for s in samples):
            report["benchmark_rejections"].append("Matching benchmark terminated early or lacks observed ticks")
            continue
        durations = [s.get("kernel_seconds") for s in samples]
        if any(type(d) not in (int, float) or not math.isfinite(d) or d <= 0 for d in durations):
            raise ValueError("Invalid benchmark kernel durations")
        per_tick = statistics.median(durations)/completed
        report["benchmark_candidates"].append({"observed_steps": completed,
                                                "median_kernel_seconds_per_tick": per_tick,
                                                "initial_counts": cfg["initial_counts"],
                                                "requested_to_observed_horizon_ratio": ticks/completed})
    if report["benchmark_candidates"]:
        estimates = [c["median_kernel_seconds_per_tick"]*ticks for c in report["benchmark_candidates"]]
        report["naive_kernel_extrapolation_seconds_per_run"] = [min(estimates), max(estimates)]
        report["naive_kernel_extrapolation_seconds_all_runs"] = [min(estimates)*replicates, max(estimates)*replicates]
    else:
        report["benchmark_rejections"].append("No complete benchmark matches the configured mechanisms and resource scales")
    return report
