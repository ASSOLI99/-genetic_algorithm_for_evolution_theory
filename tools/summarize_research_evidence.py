"""Derive descriptive research tables from a completed demographic analysis.

This is a retrospective summary, not a new experiment or an inferential test.
It reads analysis.json; it does not revalidate the individual run artifacts.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics


def summarize_group(scenarios: list[dict]) -> dict:
    strategy_names = tuple(scenarios[0]["strategies"])
    top_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    tied_top_scenarios = 0
    for scenario in scenarios:
        means = {
            name: scenario["strategies"][name]["final_abundance"]["mean"]
            for name in strategy_names
        }
        top = [name for name, value in means.items() if value == max(means.values())]
        if len(top) == 1:
            top_counts[top[0]] += 1
        else:
            tied_top_scenarios += 1
        difference = means["clone"] - means["two_parent"]
        direction = "clone_higher" if difference > 0 else "two_parent_higher" if difference < 0 else "tie"
        pair_counts[direction] += 1
    return {
        "scenarios": len(scenarios),
        "runs": sum(scenario["replicates"] for scenario in scenarios),
        "mean_final_abundance_equal_scenario_weight": {
            name: statistics.fmean(
                scenario["strategies"][name]["final_abundance"]["mean"]
                for scenario in scenarios
            )
            for name in strategy_names
        },
        "unique_highest_scenario_mean_counts": dict(top_counts),
        "tied_highest_scenarios": tied_top_scenarios,
        "clone_vs_two_parent_scenario_mean_direction": dict(pair_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.analysis.resolve(strict=True)
    output = args.output.resolve()
    if source == output:
        parser.error("Output must not replace the input analysis.")
    raw = source.read_bytes()
    analysis = json.loads(raw.decode("utf-8-sig"))
    scenarios = analysis["scenarios"]
    if analysis.get("model") != "demographic" or not scenarios:
        parser.error("Expected a nonempty demographic analysis.")
    zero = [
        scenario for scenario in scenarios
        if scenario["config"]["mating_cost"] == 0
        and scenario["config"]["extra_parent_cost"] == 0
    ]
    nonzero = [scenario for scenario in scenarios if scenario not in zero]
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_path": str(source),
        "analysis_sha256": hashlib.sha256(raw).hexdigest(),
        "source_experiment_manifest_sha256": analysis["manifest_sha256"],
        "summary_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "status": "retrospective_descriptive_summary",
        "interpretation": [
            "An ordering of observed scenario means is not a significance test.",
            "Scenarios are a chosen factorial grid, not independent samples from nature.",
            "Equal scenario weighting is a descriptive convention, not ecological prevalence.",
            "Zero cost removes the configured mating-effort surcharges, not all constraints of sex.",
            "This script does not revalidate hashes of individual run artifacts.",
        ],
        "groups": {"all": summarize_group(scenarios)},
    }
    if zero:
        result["groups"]["zero_effort_surcharge"] = summarize_group(zero)
    if nonzero:
        result["groups"]["nonzero_effort_surcharge"] = summarize_group(nonzero)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, group in result["groups"].items():
        print(name, json.dumps(group, ensure_ascii=False))
    print(f"Summary: {output}")


if __name__ == "__main__":
    main()
