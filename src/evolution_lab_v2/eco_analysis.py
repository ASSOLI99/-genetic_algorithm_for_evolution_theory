"""Scenario-specific abundance, exact census-loss times and exploratory uncertainty."""
from collections import defaultdict
import csv
import hashlib
import html
import json
import math
from pathlib import Path

import numpy as np

from .analysis import bootstrap_mean
from .artifacts import provenance, write_json
from .eco_config import STRATEGIES
from .eco_io import write_csv


def wilson(successes, n):
    if n == 0:
        return None
    z = 1.959963984540054
    p = successes/n
    centre = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0., centre-half), min(1., centre+half)]


def sign_test(differences):
    positive = sum(x > 0 for x in differences)
    negative = sum(x < 0 for x in differences)
    n = positive+negative
    p = min(1.0, 2*sum(math.comb(n, k) for k in range(min(positive, negative)+1))/(2**n)) if n else 1.0
    return {"positive": positive, "negative": negative, "ties": len(differences)-n, "p_two_sided": p}


def holm(pvalues):
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    adjusted = [1.0]*len(pvalues)
    last = 0.0
    for rank, index in enumerate(order):
        last = max(last, min(1.0, (len(pvalues)-rank)*pvalues[index]))
        adjusted[index] = last
    return adjusted


def verify_run(directory, planned, signature=None):
    directory = Path(directory)
    summary_path = directory/"summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary["complete"] or summary["config"] != planned["config"]:
        raise ValueError(f"Incomplete or mismatched run: {directory.name}")
    if signature:
        recorded = summary["manifest"]["provenance"]
        if any(recorded.get(k) != value for k, value in signature.items()):
            raise ValueError("Run source/runtime mismatch")
    if summary["tick"] > summary["horizon"] or (summary["tick"] < summary["horizon"] and summary["total_population"] != 0):
        raise ValueError("Premature nonterminal run")
    for filename, expected in summary["manifest"]["artifact_sha256"].items():
        path = directory/filename
        if path.resolve().parent != directory.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Artifact hash mismatch: {directory.name}/{filename}")
    return summary


def analyze(directory, output=None, plots=True):
    directory = Path(directory)
    manifest_path = directory/"sweep_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model") != "demographic" or manifest["status"] != "complete" or not manifest["runs"]:
        raise ValueError("Incomplete demographic experiment")
    expected_seeds = set(manifest["replicate_seeds"])
    if not expected_seeds or len(expected_seeds) != len(manifest["replicate_seeds"]):
        raise ValueError("Invalid seed plan")
    grouped = defaultdict(dict)
    input_hashes, histories = {}, {}
    # Full ledger files remain on disk and are hashed for every run. Only the
    # two predeclared trajectory scenarios need their time series in RAM.
    trace_scenarios = {manifest['scenarios'][0]['id'], manifest['scenarios'][-1]['id']} if plots else set()
    for planned in manifest["runs"]:
        path = directory/planned["path"]
        if path.resolve().parent != directory.resolve() or planned["path"] in input_hashes:
            raise ValueError("Invalid or duplicate planned run path")
        summary = verify_run(path, planned, manifest["signature"])
        input_hashes[planned["path"]] = hashlib.sha256((path/"summary.json").read_bytes()).hexdigest()
        scenario, seed = planned["scenario"], summary["config"]["seed"]
        if seed in grouped[scenario] or seed not in expected_seeds:
            raise ValueError("Duplicate/unplanned replicate")
        grouped[scenario][seed] = summary
        if scenario in trace_scenarios:
            with (path/"ledger.csv").open(newline="", encoding="utf-8") as stream:
                histories[planned["path"]] = list(csv.DictReader(stream))
    if set(grouped) != {s["id"] for s in manifest["scenarios"]} or any(set(g) != expected_seeds for g in grouped.values()):
        raise ValueError("Missing scenarios or replicate seeds")
    results, rows, survival_rows = [], [], []
    for scenario in manifest["scenarios"]:
        sid = scenario["id"]
        samples = [grouped[sid][seed] for seed in manifest["replicate_seeds"]]
        horizon = scenario["config"]["steps"]
        strategies, contrasts = {}, []
        total_extinctions = sum(r["total_population"] == 0 for r in samples)
        for s, name in enumerate(STRATEGIES):
            if scenario["config"]["initial_counts"][s] == 0:
                continue
            values = [r["strategies"][name]["population"] for r in samples]
            extinctions = sum(r["strategies"][name]["extinction_tick"] is not None for r in samples)
            conditional_shares = [r["strategies"][name]["share"] for r in samples if r["total_population"] > 0]
            entry = {"final_abundance": bootstrap_mean(values),
                     "extinction_probability": extinctions/len(samples), "extinction_ci95": wilson(extinctions, len(samples)),
                     "share_conditioned_on_population_survival": bootstrap_mean(conditional_shares) if conditional_shares else None,
                     "log_growth_conditioned_on_strategy_survival": [math.log(v/scenario["config"]["initial_counts"][s]) for v in values if v > 0],
                     "censored_extinction_runs": len(samples)-extinctions,
                     "mean_mate_failures": float(np.mean([r["strategies"][name]["cumulative"]["mate_failures"] for r in samples])),
                     "mean_encounter_failures": float(np.mean([r["strategies"][name]["cumulative"]["encounter_failures"] for r in samples])),
                     "mean_realized_newborns": float(np.mean([r["strategies"][name]["cumulative"]["realized_newborns"] for r in samples]))}
            strategies[name] = entry
            ci = entry["final_abundance"]["ci95"]
            rows.append({"scenario": sid, "strategy": name, "replicates": len(samples),
                         "mean_final_count": entry["final_abundance"]["mean"], "count_ci_low": ci[0] if ci else None,
                         "count_ci_high": ci[1] if ci else None, "extinction_probability": entry["extinction_probability"],
                         "extinction_ci_low": entry["extinction_ci95"][0], "extinction_ci_high": entry["extinction_ci95"][1],
                         "mean_mate_failures": entry["mean_mate_failures"], "mean_realized_newborns": entry["mean_realized_newborns"]})
            events = [r["strategies"][name]["extinction_tick"] for r in samples]
            for tick in range(horizon+1):
                losses = sum(t is not None and t <= tick for t in events)
                survival_rows.append({"scenario": sid, "strategy": name, "tick": tick, "replicates": len(samples),
                                      "at_risk_before_tick": sum(t is None or t >= tick for t in events),
                                      "events_at_tick": sum(t == tick for t in events), "survival_probability": 1-losses/len(samples)})
            if name != 'clone' and scenario['config']['initial_counts'][0] == scenario['config']['initial_counts'][s] and scenario['config']['initial_counts'][s] > 0:
                differences = [r['strategies'][name]['population']-r['strategies']['clone']['population'] for r in samples]
                contrasts.append({"strategy": name, "reference": "clone", "paired_final_count_difference": bootstrap_mean(differences),
                                  "sign_test": sign_test(differences)})
        adjusted = holm([r["sign_test"]["p_two_sided"] for r in contrasts])
        for contrast, p in zip(contrasts, adjusted):
            contrast["holm_p_within_scenario"] = p
        scenario_result = {"scenario": sid, "config": scenario["config"], "replicates": len(samples), "strategies": strategies,
                        "paired_contrasts": contrasts, "population_extinction_probability": total_extinctions/len(samples),
                        "population_extinction_ci95": wilson(total_extinctions, len(samples))}
        if manifest.get('experiment_kind') == 'introduced_modifier':
            name = manifest['introduced_strategy']
            introduced = [r['strategies'][name] for r in samples]
            successes = sum(r['threshold_tick'] is not None for r in introduced)
            scenario_result['introduced_modifier'] = {'strategy': name, 'introduced_count': scenario['config']['initial_counts'][STRATEGIES.index(name)],
                                                      'threshold': scenario['config']['establishment_size'], 'introductions': len(samples),
                                                      'establishment_probability': successes/len(samples), 'establishment_ci95': wilson(successes, len(samples)),
                                                      'threshold_times_conditional_on_crossing': [r['threshold_tick'] for r in introduced if r['threshold_tick'] is not None],
                                                      'fixation_probability': sum(r['fixation_tick'] is not None for r in introduced)/len(samples),
                                                      'established_then_extinct': sum(r['threshold_tick'] is not None and r['extinction_tick'] is not None for r in introduced),
                                                      'interpretation': 'Conditional on this designed compatible introduction; does not estimate the origin of the reproductive machinery.'}
        results.append(scenario_result)
    report = {"model": "demographic", "name": manifest["name"], "primary_endpoint": manifest['primary_endpoint'],
              "provenance": provenance(), "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "input_summary_sha256": input_hashes, "bootstrap_seed": 73021, "bootstrap_draws": 2000,
              "inference": "Exploratory scenario-specific model comparison; unadjusted descriptive bootstrap CIs. Exact paired sign tests with Holm correction within each scenario only. No universal winner, biological calibration, or correction across scenarios.",
              "scenarios": results}
    write_csv(directory/"comparison.csv", rows)
    write_csv(directory/"survival_curves.csv", survival_rows)
    write_csv(directory/"scenario_index.csv", [{"scenario": s["id"], "factors": s["factors"], "full_config": s["config"]} for s in manifest["scenarios"]])
    report["figures"] = make_plots(directory, report, manifest, histories, survival_rows) if plots else []
    write_json(output or directory/"analysis.json", report)
    write_report(directory, report, manifest)
    return report


def make_plots(directory, report, manifest, histories, survival_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figures = []
    def save(fig, name):
        for extension in ("png", "svg"):
            filename = f"{name}.{extension}"
            fig.savefig(directory/filename, dpi=150, bbox_inches="tight", **({"metadata": {"Date": None}} if extension == "svg" else {}))
        figures.append(name+".png")
        plt.close(fig)
    for first in range(0, len(report["scenarios"]), 36):
        block = report["scenarios"][first:first+36]
        values = np.array([[s["strategies"].get(name, {}).get("final_abundance", {}).get("mean", np.nan) for name in STRATEGIES] for s in block])
        fig, axis = plt.subplots(figsize=(10, max(3, len(block)*.3)))
        color = axis.imshow(values, aspect="auto", cmap="viridis", vmin=0)
        axis.set_xticks(range(len(STRATEGIES)), STRATEGIES, rotation=25, ha="right")
        axis.set_yticks(range(len(block)), [s["scenario"] for s in block])
        axis.set_title("Mean final census by scenario (not a universal ranking)")
        fig.colorbar(color, ax=axis, label="Individuals; uncertainty in comparison.csv")
        save(fig, f"final_abundance_{first//36+1}")
    # Selected by plan position before observing outcomes.
    selected = list(dict.fromkeys([manifest["scenarios"][0]["id"], manifest["scenarios"][-1]["id"]]))
    for sid in selected:
        scenario = next(s for s in manifest["scenarios"] if s["id"] == sid)
        horizon = scenario["config"]["steps"]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for s, name in enumerate(STRATEGIES):
            if scenario["config"]["initial_counts"][s] == 0:
                continue
            traces = []
            for run in [r for r in manifest["runs"] if r["scenario"] == sid]:
                trace = np.zeros(horizon+1)
                trace[0] = scenario["config"]["initial_counts"][s]
                for row in histories[run["path"]]:
                    if row["strategy"] == name:
                        trace[int(row["tick"])] = int(row["end"])
                traces.append(trace)
            axes[0].plot(range(horizon+1), np.mean(traces, axis=0), label=name)
            curve = [r["survival_probability"] for r in survival_rows if r["scenario"] == sid and r["strategy"] == name]
            axes[1].step(range(horizon+1), curve, where="post", label=name)
        axes[0].set(xlabel="Tick", ylabel="Mean census", title=f"{sid}: abundance trajectories")
        axes[1].set(xlabel="Tick", ylabel="Survival probability", ylim=(-.02, 1.02), title="Exact census-loss events; end censoring")
        axes[1].legend(fontsize=8, loc="center left", bbox_to_anchor=(1.02, .5))
        fig.tight_layout()
        save(fig, f"trajectories_{sid}")
    return figures


def write_report(directory, report, manifest):
    parts = [f"# Evolution Lab — {report['name']}", "", "Exploratory results under explicit hypothetical assumptions. No universal reproductive winner is inferred.",
             "", f"Completed {len(manifest['runs'])} runs across {len(report['scenarios'])} scenarios. See scenario_index.csv for the factor map, comparison.csv for all intervals, and analysis.json for paired contrasts and provenance.",
             "", "Final counts include extinct runs as zero. Population shares condition on total population survival; zero denominators remain undefined. Extinction times are exact discrete census times, with survivors censored at the configured horizon.",
             "", "Bootstrap intervals are descriptive and unadjusted. Paired sign-test p-values use Holm correction within a scenario, not across this exploratory scenario grid. Small replicate counts are imprecise.", ""]
    parts.extend([f"Primary endpoint: {report['primary_endpoint']}. Abundance plots are secondary for introduction experiments.", ""])
    introduction_html = ''
    if manifest.get('experiment_kind') == 'introduced_modifier':
        parts.extend(['| Scenario | Introductions | Threshold-crossing probability | Wilson 95% CI | Fixation probability |', '|---|---:|---:|---|---:|'])
        intro_rows = []
        for scenario in report['scenarios']:
            result = scenario['introduced_modifier']
            ci = result['establishment_ci95']
            cells = [scenario['scenario'], str(result['introductions']), f"{result['establishment_probability']:.3f}", f"[{ci[0]:.3f}, {ci[1]:.3f}]", f"{result['fixation_probability']:.3f}"]
            parts.append('| '+' | '.join(cells)+' |')
            intro_rows.append('<tr>'+''.join(f'<td>{html.escape(c)}</td>' for c in cells)+'</tr>')
        parts.append('')
        introduction_html = '<h2>Designed introductions: threshold crossing, not origin probability</h2><table><tr><th>Scenario</th><th>Introductions</th><th>Probability</th><th>Wilson 95% CI</th><th>Fixation probability</th></tr>'+''.join(intro_rows)+'</table>'
    for name in report["figures"]:
        parts.extend([f"![{name}]({name})", ""])
    parts += ["| Scenario | Strategy | Mean final count | Descriptive 95% CI | Extinction probability |", "|---|---|---:|---|---:|"]
    table_rows = []
    for scenario in report["scenarios"]:
        for name, entry in scenario["strategies"].items():
            mean, ci = entry["final_abundance"]["mean"], entry["final_abundance"]["ci95"]
            interval = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "undefined (n=1)"
            cells = [scenario["scenario"], name, f"{mean:.2f}", interval, f"{entry['extinction_probability']:.3f}"]
            parts.append("| " + " | ".join(cells) + " |")
            table_rows.append("<tr>"+"".join(f"<td>{html.escape(c)}</td>" for c in cells)+"</tr>")
    (directory/"REPORT.md").write_text("\n".join(parts)+"\n", encoding="utf-8")
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Evolution Lab comparison</title>
<style>body{{font:16px system-ui;max-width:1250px;margin:40px auto;padding:0 20px;color:#18242d}} img{{max-width:100%}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #ddd;padding:7px;text-align:left}}th{{background:#e9f0f4}}p{{line-height:1.6}}a{{color:#176a8d}}</style>
<h1>Evolution Lab — {html.escape(report['name'])}</h1>
<p dir="rtl">هاي نتائج استكشافية حسب فرضيات المحاكاة. اختلاف النتيجة بين السيناريوهات مهم، وما بنستنتج منها تفوّق دائم لأي طريقة تكاثر. عدد السكان النهائي يشمل الجماعات اللي انقرضت، والهوامش بتوضح عدم اليقين.</p>
<p>{html.escape(parts[4])}</p><p>{html.escape(parts[6])}</p><p>{html.escape(parts[8])}</p>
<p>Primary endpoint: {html.escape(report['primary_endpoint'])}</p>{introduction_html}
<p><a href="scenario_index.csv">Scenario factors</a> · <a href="comparison.csv">All counts and intervals</a> · <a href="analysis.json">Statistics and provenance</a></p>
{''.join(f'<img src="{html.escape(name)}" alt="{html.escape(name)}">' for name in report['figures'])}
<table><thead><tr><th>Scenario</th><th>Strategy</th><th>Mean final count</th><th>Descriptive 95% CI</th><th>Extinction probability</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></html>"""
    (directory/"REPORT.html").write_text(document, encoding="utf-8")
