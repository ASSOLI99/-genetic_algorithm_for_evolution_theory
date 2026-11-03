<p align="center">
  <img src="docs/images/banner.png" alt="Evolution Lab — clones vs. two parents vs. four and eight parents" width="100%">
</p>

<p align="center">
  <a href="https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory/actions/workflows/tests.yml"><img src="https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&logoColor=white" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/tests-135%20passing-2ea44f" alt="135 tests">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational" alt="platforms">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT license"></a>
</p>

<p align="center">
  <b>English</b> · <a href="README.ar.md">العربية</a>
</p>

---

**Evolution Lab** is an open-source simulator that asks one of biology's oldest puzzles:

> **Why do most complex organisms reproduce with two parents, when copying yourself is twice as fast?**

It drops seven reproduction strategies into the *same* small world — shared food, a changing environment, parasites, aging and death — and lets them compete. Then it shows you, with charts and honest uncertainty, who grew, who shrank and who went extinct. It even tests *invented* four- and eight-parent systems to ask "why two and not more?".

Everything is reproducible: the same seed gives the same result, every run is saved with checkpoints, and 135 automated tests check the bookkeeping before any experiment starts.

## ⬇️ Download and run in 2 minutes

**1. Install Python 3.13 or newer** from [python.org](https://www.python.org/downloads/) (on Windows, tick **"Add python.exe to PATH"**).

**2. Download the project**

| Option | How |
|---|---|
| 📦 **Ready-made zip** | [**Evolution-Lab-v0.2.0.zip**](https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory/raw/main/release/Evolution-Lab-v0.2.0.zip) — then right-click → *Extract All* |
| 🟢 GitHub button | **Code → Download ZIP** at the top of this page |
| 🧑‍💻 Git | `git clone https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory.git` |

**3. Start it**

| System | What to do |
|---|---|
| 🪟 **Windows** | Double-click **`START-WINDOWS.bat`** and press <kbd>Enter</kbd> |
| 🍎 **macOS** / 🐧 **Linux** | Open a terminal in the folder and run `./start.sh` |

That's it. The first run creates a private environment (`.venv`), installs the exact library versions, runs the test suite, runs the experiment and **opens a report in your browser**. Nothing is installed system-wide. Results are saved in the `runs/` folder.

<p align="center">
  <img src="docs/images/terminal.png" alt="The launcher running the quick demo" width="85%">
</p>

### Experiment profiles

| Menu | `start.sh` argument | What it does | Size |
|:---:|---|---|---|
| **1** | `smoke` *(default)* | Quick demo — checks everything works | 4 scenarios × 2 replicates, ~1 min |
| **2** | `standard` | The full prepared comparison | 144 scenarios × 8 replicates (1,152 runs), ~5–15 min |
| **3** | `isolated` | Each strategy alone, same starting size | 42 scenarios × 8 replicates |
| **4** | `invasion` | 8 "sometimes-sexual" mutants dropped among 216 clones | 4 scenarios × 16 replicates, 200 steps |

## 📸 Screenshots

<table>
<tr>
<td width="50%"><img src="docs/images/report.png" alt="HTML report"><br><sub><b>The report</b> opens automatically: summary, charts and a table with uncertainty for every scenario.</sub></td>
<td width="50%"><img src="docs/images/trajectories.png" alt="Population trajectories"><br><sub><b>Population over time</b> (left) and <b>survival curves</b> (right) in the harshest world (mating costs, drifting environment, tracking parasites): in this run, clones and facultative mixers grew while the 4- and 8-parent systems collapsed.</sub></td>
</tr>
<tr>
<td colspan="2" align="center"><img src="docs/images/heatmap.png" alt="Final population heatmap" width="70%"><br><sub><b>Final population by scenario</b> — each row is one world (costs × environment × parasites × …). Brighter = more individuals left at the end. The winner changes with the world, which is exactly the point.</sub></td>
</tr>
</table>

## 🧬 The idea

Sexual reproduction looks like a bad deal. A clone passes on 100 % of its genes and every individual can have babies; a sexual organism must find a compatible partner, pays a mating cost, and passes on only half of its genes. So why is sex everywhere?

Classic hypotheses say mixing genes pays off when **the environment keeps changing** or when **parasites keep adapting** to the most common genotype (the *Red Queen* idea). Evolution Lab turns those ideas into a controlled experiment you can run and rerun.

### The seven contestants

| Strategy | How it reproduces |
|---|---|
| 🔵 `clone` | Copies its whole genome — no partner needed |
| 🟠 `two_parent` | Always needs a partner; offspring get a recombined half from each parent |
| 🟢 `facultative` | Usually clones, mixes with an inherited, *evolvable* probability |
| 🔴 `periodic` | Mixes on a fixed schedule, clones otherwise |
| 🟣 `stress` | Mixes only when it is doing badly in the current environment |
| 🟤 `four_parent` | **Invented:** every child has 4 genetic parents |
| 🩷 `eight_parent` | **Invented:** every child has 8 genetic parents |

The 4/8-parent systems don't exist in nature; they are "what-if" mechanisms (two different inheritance rules are tested) to ask whether *more* mixing would be even better — or whether finding many partners costs too much.

### How one time step works

```mermaid
flowchart LR
    A[🌍 Environment<br/>& parasites change] --> B[💀 Aging &<br/>random death]
    B --> C[🍞 Shared food renews;<br/>everyone pays upkeep]
    C --> D[💞 Adults look for<br/>compatible partners]
    D --> E[🧬 Children inherit<br/>genes + mutations]
    E --> F[🏠 Food & space lottery<br/>decides who is born]
    F --> G[📊 Census, ledgers<br/>& checkpoints]
    G --> A
```

- **Genomes** are diploid (two copies of each chromosome), with real recombination, dominance and mutation.
- **Fitness** = how well an individual's genes match the current environment, minus the damage from parasites that target common genes.
- **Fair costs:** every strategy gets the same expected reproductive effort; mixing strategies pay declared mating and extra-partner costs (the grid also tests zero-cost worlds).
- **Strict accounting:** food and population are balanced every step (`after = before + renewal − spending`). If anything doesn't add up, the run stops instead of producing silent errors.

### What gets varied (the standard comparison)

`mating cost (0 / 0.2)` × `extra-partner cost (0 / 0.04)` × `environment (static / periodic / random drift)` × `parasites (none / fixed / tracking)` × `4/8-parent rule (2 kinds)` × `who can mate with whom (2 kinds)` = **144 worlds**, each replayed 8 times with independent seeds.

## 📂 What you get after a run

```
runs/smoke_20261103_062550/
├── REPORT.html          ← open this
├── REPORT.md
├── comparison.csv       every number + confidence intervals
├── scenario_index.csv   which settings each scenario used
├── analysis.json        statistics, seeds, file fingerprints
├── final_abundance_*.png/svg, trajectories_*.png/svg
└── S000_R000/ ...       per-run metrics, ledgers, events, full parentage, checkpoints
```

Interrupted? Run again with the same folder and it resumes from the last checkpoint:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-Experiment.ps1 -Profile standard -Output '.\runs\YOUR_FOLDER' -Resume
```

## 🛠️ For developers

<details>
<summary><b>Manual setup and command-line interface</b></summary>

```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe   macOS/Linux: .venv/bin/python
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

```bash
# Show an experiment plan without running it
python -m evolution_lab_v2 experiment --config configs/comparison_ready.json --plan-only
# Run / resume a batch
python -m evolution_lab_v2 experiment --config configs/comparison_smoke.json --output runs/my_run
python -m evolution_lab_v2 experiment --config configs/comparison_smoke.json --output runs/my_run --resume
# Small fixed-size reference engine (clone vs. two parents)
python -m evolution_lab_v2 simulate --config configs/neutral_two_parent.json --output runs/two_parent
python -m evolution_lab_v2 sweep --config configs/neutral_clone.json --grid configs/neutral_grid.json --replicates 4 --seed 20261020 --output runs/neutral_pilot
python -m evolution_lab_v2 analyze --input runs/neutral_pilot --output runs/neutral_pilot/analysis_repeat.json
python -m evolution_lab_v2 benchmark --config configs/neutral_clone.json --sizes 100,500,1000 --generations 10 --repeats 3 --output reports/benchmark_reference.json
# Integrity audit of the preserved original simulation
python tools/audit_baseline.py
```

Output directories must be new. Resume requires the same config, code, protocol files and library versions — this is what makes results reproducible.

To build your own experiment, copy a file in `configs/` and change the `grid`. Unknown or unsafe settings are rejected with a clear error.

The repository ships source, tests, configs and methods. Generated runs, the historical v0.1 results CSV and unpublished research notes are not distributed; the two tests that compare against that CSV are skipped when it is absent, while source-integrity and determinism checks still run.

</details>

<details>
<summary><b>Project layout</b></summary>

```
├── START-WINDOWS.bat        one-click launcher (Windows)
├── start.sh                 one-click launcher (macOS / Linux)
├── Start-Experiment.ps1     PowerShell launcher with resume support
├── configs/                 ready-made experiments (JSON)
├── src/evolution_lab_v2/
│   ├── ecology.py           the demographic engine (7 strategies, food, parasites)
│   ├── eco_genetics.py      2/4/8-parent inheritance rules
│   ├── eco_experiment.py    batch plans, seeds, resume
│   ├── eco_analysis.py      statistics, charts, HTML report
│   ├── model.py, genetics.py  fixed-size mathematical reference engine
│   └── cli.py               command-line interface
├── tests/                   135 automated tests
├── tools/                   baseline audit and evidence summaries
└── evolution_lab_verified.py  original v0.1 simulation, byte-preserved
```

</details>

### Documentation

| File | Read it for |
|---|---|
| [`ECO_MODEL.md`](ECO_MODEL.md) | Exact definition of the ecological model and every assumption |
| [`ECO_PROTOCOL.md`](ECO_PROTOCOL.md) | The experiment design, endpoints and statistics, fixed before running |
| [`LIMITATIONS.md`](LIMITATIONS.md) | What this model can **not** tell you |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Code structure and development gates |
| [`MODEL_ASSUMPTIONS.md`](MODEL_ASSUMPTIONS.md) · [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | The fixed-size reference engine |
| [`RUN_ME_AR.md`](RUN_ME_AR.md) | Detailed run guide in Arabic |

## ⚠️ Read before drawing conclusions

This is a **toy model with transparent, declared assumptions** — not a calibrated model of any real species. Eight replicates give an exploratory, imprecise comparison. The four- and eight-parent systems are invented. A strategy "winning" in some scenarios means *"under these assumptions"*, never *"this is how nature works"*. See [`LIMITATIONS.md`](LIMITATIONS.md).

## 🤝 Contributing

Ideas, new experiment configs, better charts and translations are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and open an [issue](https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory/issues).

## 📄 License and citation

Released under the [MIT License](LICENSE). If you use it in research or teaching, see [`CITATION.cff`](CITATION.cff).
