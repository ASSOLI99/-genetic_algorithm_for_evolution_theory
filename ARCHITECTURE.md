# V2 architecture and phase gates

V2 lives in `src/evolution_lab_v2`; baseline imports are confined to audit tooling/tests. No existing baseline implementation is reused as if it were a diploid model.

| Component | Current role |
|---|---|
| `config.py` | Immutable strict JSON configuration, explicit model choices and pilot work limits. Unsupported ecological/cost/strategy fields are errors. |
| `genetics.py` | Finite exact sequential weighted sampling and phased diploid gamete formation. 1/2/4/8 sampling tests do not imply implemented 4/8 genetics. |
| `model.py` | Fixed-census clone/two-parent reference, pure observation, retained per-offspring parent identities. |
| `artifacts.py` | Source/runtime provenance, atomic JSON/checkpoint replacement, non-pickle state and exact resume. |
| `cli.py` | validate/simulate/sweep/analyze/benchmark entry points, progress, workload guards, no overwrite of simulation directories. |
| `analysis.py` | Scenario-specific pilot bootstrap and founder-paired contrasts. No biological superiority classifier. |
| `tools/audit_baseline.py` | Source integrity against `baseline_sha256.json`; historical replay and CSV/schema/seed audit when the optional local CSV is available. |

Gate 1: complete audit, original tests, all-run full replay, additional regression coverage, integrity hashes, runnable reproducibility tooling and this architecture.

Gate 2: implemented diploid clone/two-parent mathematical reference, zero-cost/equal-output controls, linked gametes, dominance, mutation, neutral mean/variance checks, parentage and checkpoint replay. This satisfies the reference submilestone, not calibrated ecological realism or nonzero energetic matching. It is intentionally a separate engine; a fixed census cannot support extinction/invasion conclusions.

Gate 3: v0.2 implements a separate nonWF engine (`ecology.py`, `eco_config.py`, `eco_genetics.py`) with persistent IDs, age/maturity/senescence, overlapping cohorts, survival, explicit shared resources, expected focal effort costs, encounter failures and configurable mating-type/program compatibility. It records every-step accounting, exact census-loss/fixation events and candidate ancestry/contribution/recruitment. Seven programs include facultative modifier inheritance and two clearly invented four/eight-parent mechanisms. The reference remains separate; expected focal effort does not constitute a hard donor energy budget.

Gate 4: the exploratory E2/E4/E5 grid and designed E3 introduction are specified in `ECO_PROTOCOL.md` before readiness pilots. Separate RNG streams, synthetic environmental/parasite sensitivities, resource renewal, scenario-specific abundance/survival/introduction analysis, LD/lag diagnostics, full replay, batch resume and PNG/SVG/HTML reports are implemented in `eco_io.py`, `eco_experiment.py` and `eco_analysis.py`. The common anchored uniform sampler is O(births × k²), tested against exact uniform conditionals. `Start-Experiment.ps1` verifies dependencies/tests, then runs the frozen plan. Calibrated parameters, migration, population/genome/horizon convergence, independent engine verification, precision/power estimates and confirmatory/held-out design remain open gates.

Gate 5: run powered sweeps progressively only after correctness, convergence, profile, storage and checkpoint gates. Use 10k→100k→1m only when estimates and user consent for expensive workloads justify it. E6 independently validates held-out configurations and relevant external simulators/data. Report failures and uncertainty across mechanisms.

The repository publishes implementation, tests, configurations and methods. Generated runs, historical CSV data, analysis reports and local research notes are excluded. The original baseline source remains byte-preserved; only comparisons against unavailable historical CSV data are skipped in a fresh checkout. This phase boundary avoids presenting a partially tested ecological engine as evidence about the origin or general advantage of reproduction.
