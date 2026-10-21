# Evolution Lab V2

An auditable computational-evolution research prototype. V0.2 adds a tested demographic comparison of seven reproductive programs, overlapping cohorts, explicit resources, compatibility, facultative modifiers and two hypothetical 4/8-parent mechanisms. The small diploid analytical reference remains separate. No reproductive winner or empirical biological calibration is assumed.

This release publishes source code, tests, configurations and methods. Generated runs, checkpoints, historical results, analysis reports and unpublished research notes remain local and are excluded by `.gitignore`. Analysis and reporting code is included so users can generate their own outputs.

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

```powershell
.\.venv\Scripts\python.exe -m evolution_lab_v2 sweep --config configs\neutral_clone.json --grid configs\neutral_grid.json --replicates 4 --seed 20261020 --output runs\neutral_pilot
.\.venv\Scripts\python.exe -m evolution_lab_v2 analyze --input runs\neutral_pilot --output runs\neutral_pilot\analysis_repeat.json
.\.venv\Scripts\python.exe -m evolution_lab_v2 benchmark --config configs\neutral_clone.json --sizes 100,500,1000 --generations 10 --repeats 3 --output reports\benchmark_reference.json
```

The reference sweep freezes its grid and seed plan before running. Paired founders improve comparability, but the streams diverge after inheritance differs. `analysis.json` reports final gene-diversity diagnostics, descriptive replicate intervals and paired contrasts. Diversity is not a measure of universal superiority. The historical 16-run reference pilot is software validation, not a powered ecological experiment.

The reference benchmark excludes checkpoint/CSV I/O and includes tracemalloc overhead. Its weighted sampler is O(N²); the new ecological uniform anchored sampler is O(births × k²), and ecological benchmarks separately include checkpoint/log I/O and trace memory. Neither justifies extrapolation to million-individual feasibility. Config limits reject such runs and excessive comparison workloads. See `LIMITATIONS.md` for scientific limits. Existing analysis results and research conclusions are not included in this code release.
