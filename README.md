# Evolution Lab V2

An auditable computational-evolution research prototype. V0.2 adds a tested demographic comparison of seven reproductive programs, overlapping cohorts, explicit resources, compatibility, facultative modifiers and two hypothetical 4/8-parent mechanisms. The small diploid analytical reference remains separate. No reproductive winner or empirical biological calibration is assumed.

V0.3 adds strategy-neutral catastrophe mortality, drought stock/renewal shocks, independent onset schedules, exact drought/checkpoint replay and a calendar/workload planner. The base life cycle is extended by [DISTURBANCE_PROTOCOL.md](DISTURBANCE_PROTOCOL.md). Version 0.2 checkpoints require version 0.2 code; migration is not implicit.

This release publishes source code, tests, configurations and methods. Generated runs, checkpoints, historical results, analysis reports and unpublished research notes remain local and are excluded by `.gitignore`. Analysis and reporting code is included so users can generate their own outputs.

## Live graphical laboratory

Version 0.7 retains a choice between shared competition and isolated worlds. Isolation gives each of seven programs its own population/food/capacity in each environment (21 worlds), with common configurable founding counts and budgets, paired initial conditions, globally synchronized manual catastrophes and per-environment live comparisons. Shared competition preserves the previous behavior. The Arabic dashboard includes population/resource charts, actual individual/genome inspection, detailed strategy metrics, pause/resume/speed controls and local exports. Isolation uses more total resources and asks a different persistence question. GUI ledger-memory guards can reduce available actual updates; the estimate dialog displays the work before acknowledgement.

The community table includes exact extinction updates and mapped scenario times, with ongoing/censored observations for surviving strategies. A separate survival CSV export covers all environments. Frontend survival-contract checks run with `node --test tests/gui_survival.test.cjs` when Node.js is available; Node is not needed to run the dashboard.

Start from the checkout:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-GUI.ps1
# Or, with the project already installed:
.\.venv\Scripts\python.exe -m evolution_lab_v2 gui --port 8765
```

The service binds only to `http://127.0.0.1:8765`. It needs no external frontend libraries, accounts, CDN or hosting. Before starting, users acknowledge a CPU/RAM/browser-resource notice. Display durations begin at one million **scenario years**; actual computation is separately bounded and explicitly shown. The clock is not calibrated geological time. The global catastrophe policy permits one active event, followed by at least eight million scenario years of cooldown after its end, rounded up to complete updates. Pause freezes both clocks. A lost UI heartbeat pauses processing after 20 seconds.

Before starting shared competition, use the seven checkboxes to choose participating programs (at least one). Unchecked programs receive zero founders and never enter the simulation. They are excluded from live curves/tables and survival risk sets; the selection is saved and replayed. Each selected program keeps its configured founding count, with no redistribution; shared capacity and food budgets remain as declared. All-seven defaults preserve previous trajectories. Isolation continues to compare all seven separate program worlds.

In shared competition, select an environment card and reproductive program in the competitor-removal panel. Remove all living members in that environment, or choose all shared environments. Removal executes before the next update's ordinary dynamics; paused sessions require resume. Capacity and food budgets stay unchanged, with no food refund. A separate counter, exact census marker, intervention journal and survival loss-cause fields distinguish experimental removal from natural extinction. It cannot overlap an active catastrophe or another queued removal.

Normal completion/stop and manual export save a local HTML report, environment checkpoints/metrics/ledgers, history and an exact intervention journal in `runs/gui_*`, with a downloadable ZIP. `replay_session` in `gui_session.py` reproduces the recorded biological state and RNG/resource fingerprints under the same source/runtime. Single adaptive interactive sessions are descriptive; they are not independent statistical replicates. See [GUI_PROTOCOL.md](GUI_PROTOCOL.md) for the full time, resource, model and replay contract. Full offspring parentage is disabled in live sessions to bound memory; genomes remain in checkpoints.

## Audit survival accounting and competition

The bounded diagnostic design in `SURVIVAL_AUDIT_PROTOCOL.md` checks the existing life cycle with neutral, compatibility, competition, crossover and isolated-population controls. It does not change engine parameters or calibrate them to a species. Freeze and inspect its 168-run plan, then execute/resume the same plan:

```powershell
.\.venv\Scripts\python.exe tools\audit_survival.py --output runs\my_survival_audit --plan-only
.\.venv\Scripts\python.exe tools\audit_survival.py --output runs\my_survival_audit --resume
```

`SURVIVAL_SMALL_FOUNDERS_PROTOCOL.md` defines a separate equal-program-founder control after the primary audit; it retains the primary plan and enforces their combined workload guard. Invoke it from the checkout with `python -m tools.audit_survival_smallfounders --primary runs\my_survival_audit --output runs\my_smallfounders_audit`. Outputs, including plans, seeds, all outcomes, checkpoints, accounting checks and descriptive uncertainty, remain local under `runs/`. Independent age-survival, neutral-fecundity, census-lottery and persisted-ledger checks are included in the Python test suite.

## Run the prepared comparison

Arabic instructions: `RUN_ME_AR.md`. The PowerShell launcher verifies pinned dependencies, runs the test suite, freezes the plan, runs/resumes the batch and opens a local HTML report with PNG/SVG figures.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1
```

The default exploratory comparison is 144 scenarios × eight replicate blocks × 80 demographic steps, with populations capped at 336, not millions. It includes zero/nonzero initiation and contributor costs, three environment regimes, three parasite regimes, both hypothetical mechanisms and both compatibility scopes. Exact scientific definitions and statistical limits are in `ECO_PROTOCOL.md` and `ECO_MODEL.md`. `--plan-only` does not run simulations:

```powershell
.\.venv\Scripts\python.exe -m evolution_lab_v2 experiment --config configs\comparison_ready.json --plan-only
# Small end-to-end check; exercised during development:
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1 -Profile smoke -NoOpen
# Resume the original batch with identical code/config/runtime:
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1 -Output 'runs\YOUR_ORIGINAL_DIRECTORY' -Resume
```

Separate `-Profile isolated` controls test one program per patch at equal total census; `-Profile invasion` tests a designed rare facultative introduction, not the origin of mating. Outputs include a readable `REPORT.html`, Markdown report, every scenario's CSV/JSON statistics, exact extinction events, ledgers, compressed full parentage and checkpoints. Failed/incomplete or hash-mismatched runs cannot silently enter analysis. Interrupted attempts are preserved when resuming.

Read `ECO_PROTOCOL.md`, `ECO_MODEL.md`, `MODEL_ASSUMPTIONS.md`, `EXPERIMENT_PROTOCOL.md`, `LIMITATIONS.md` and `ARCHITECTURE.md` before interpreting results. The original simulation and tests are preserved. The historical CSV and previous reports are not distributed. Commands below describe the preserved mathematical reference and optional historical audit workflow.

## Windows PowerShell setup

Use Python 3.13 or later. Clone the repository and run commands from its checkout:

```powershell
git clone https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory.git
Set-Location -LiteralPath '.\-genetic_algorithm_for_evolution_theory'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

No activation or execution-policy change is required. Development dependencies are pinned, including transitive test dependencies; setuptools build version is pinned in `pyproject.toml`.

## Audit and tests

```powershell
python test_evolution_lab.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\audit_baseline.py
# Optional complete historical replay; requires the original local CSV:
.\.venv\Scripts\python.exe tools\audit_baseline.py --full --output reports\baseline_audit_full.json
.\.venv\Scripts\python.exe -m evolution_lab_v2 validate --config configs\neutral_clone.json
```

The audit checks preserved source against `baseline_sha256.json`. If the original matching `results_10k.csv` is available locally, it also checks all records and replays the first 200 generations of all ten historical seeds; `--full` requires the CSV and replays all generations. Reports are generated locally under the ignored `reports/` directory. The test suite includes the two original tests plus baseline characterization, inheritance, property-based sampling, one-step neutral mean/variance, checkpoint, artifact and CLI tests. Only the two historical-CSV comparisons are skipped when that unpublished file is absent; source integrity and determinism checks remain active. Known baseline defects are characterized, not repaired in place.

## Small simulation and exact resume

```powershell
.\.venv\Scripts\python.exe -m evolution_lab_v2 simulate --config configs\neutral_two_parent.json --output runs\two_parent
.\.venv\Scripts\python.exe -m evolution_lab_v2 simulate --config configs\neutral_two_parent.json --output runs\partial --stop-after 23
.\.venv\Scripts\python.exe -m evolution_lab_v2 simulate --config configs\neutral_two_parent.json --output runs\resumed --resume runs\partial\checkpoint.npz
```

Output directories must be new; select a fresh name for repeated commands. Resume requires the same complete config, code/protocol hashes and runtime signature. Checkpoints contain binary genomes, full parentage, RNG state and sampled metrics. New output contains `metrics.csv`, `parentage.csv`, `summary.json`, `manifest.json` and `checkpoint.npz`. CSV parent IDs are qualified by generation; metric allele frequencies are JSON-compatible list fields. Progress is printed at checkpoint boundaries. A failure leaves the last atomic checkpoint available; resume into a new directory.

## Pilot sweep, analysis and benchmark

For the new bounded catastrophe comparison (16 scenarios × four repeats × 400 census updates):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1 -Profile catastrophe -PlanOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1 -Profile catastrophe
```

To plan a hypothetical calendar horizon without launching it:

```powershell
.\.venv\Scripts\python.exe -m evolution_lab_v2 plan-time --config configs\catastrophe_benchmark.json --years 100000000 --years-per-step 1 --replicates 8 --output reports\deep_time_plan.json
```

The calendar mapping is a user assumption requiring biological calibration. The planner reports workload and two preallocated arrays' memory, not total memory or biological generations. It does not bypass the existing workload limits. Optional `--benchmark` uses only matching, complete source/runtime measurements for a labeled naive kernel extrapolation; it does not establish long-run feasibility. Read the extension protocol before interpreting catastrophe results or planning deep-time work.

```powershell
.\.venv\Scripts\python.exe -m evolution_lab_v2 sweep --config configs\neutral_clone.json --grid configs\neutral_grid.json --replicates 4 --seed 20261020 --output runs\neutral_pilot
.\.venv\Scripts\python.exe -m evolution_lab_v2 analyze --input runs\neutral_pilot --output runs\neutral_pilot\analysis_repeat.json
.\.venv\Scripts\python.exe -m evolution_lab_v2 benchmark --config configs\neutral_clone.json --sizes 100,500,1000 --generations 10 --repeats 3 --output reports\benchmark_reference.json
```

The reference sweep freezes its grid and seed plan before running. Paired founders improve comparability, but the streams diverge after inheritance differs. `analysis.json` reports final gene-diversity diagnostics, descriptive replicate intervals and paired contrasts. Diversity is not a measure of universal superiority. The historical 16-run reference pilot is software validation, not a powered ecological experiment.

The reference benchmark excludes checkpoint/CSV I/O and includes tracemalloc overhead. Its weighted sampler is O(N²); the new ecological uniform anchored sampler is O(births × k²), and ecological benchmarks separately include checkpoint/log I/O and trace memory. Neither justifies extrapolation to million-individual feasibility. Config limits reject such runs and excessive comparison workloads. See `LIMITATIONS.md` for scientific limits. Existing analysis results and research conclusions are not included in this code release.
