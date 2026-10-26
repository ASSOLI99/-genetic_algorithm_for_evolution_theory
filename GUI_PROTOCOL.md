# Local interactive laboratory v0.4 — scientific and interaction contract

Date: 2026-10-26. This interface wraps the existing demographic engine. The nuclear genetics, reproductive costs and ecological accounting are unchanged. It adds local interaction, not a calibrated geological model. Generated results remain private under ignored `runs/`.

## Time, scale and resources

The duration input accepts at least one million **scenario-display years**. This is a declared display scale, not empirical biological time. The user separately chooses 100..5,000 actual census updates. The displayed years per update equal scenario duration divided by actual updates. Thus larger displayed durations do not secretly trigger millions of iterations or add uncomputed biological events. The UI displays both clocks and an uncalibrated-time notice before, during and after a run. Changing the displayed duration alone does not recalibrate mortality, maturity, mutation, environment or other model rates. Per-individual ages are shown in updates rather than years.

The interface has no low arbitrary scenario-duration ceiling in its form; finite numeric precision bounds still apply. Values above 24 decimal orders of magnitude in millions of years are rejected. The computational budget remains bounded independently: capacities 168/336/672, three environments at most, existing per-run and batch individual/locus update guards, parentage recording off, 16 binary loci, and up to 60 actual updates/second. Resolution exceeding the existing engine budget is rejected. Display duration is not permission to bypass the guards.

Before each run, the interface requests acknowledgement of a CPU/RAM/browser-resource notice and displays actual updates, capacity-related work, calendar mapping and approximate qualitative load. The backend rejects an unacknowledged start. It makes no hardware-specific memory or runtime promise. The dashboard reports Python process working-set memory when available on Windows and CPU time as a percentage of one core, not total machine CPU or browser memory. Animation and chart rendering have separate browser costs.

## Environments and data

Static, periodic and autocorrelated environments are separate populations, each with all seven existing programs and equal initial counts. Resource budgets scale with configured census capacity. Matching seeds supply paired founders and external draws as applicable; these are scenarios, not independent statistical replicates. The three panels have no migration between them. Their decorative terrain and dot positions are visual only.

Each displayed dot represents an actual sampled individual ID, strategy, age and genome from its environment. At most 140 are shown per panel, sampled deterministically without consuming the model RNG. Clicking a dot shows its real binary model genome, not a fabricated DNA sequence. Population values and curves use all modeled individuals. Empty/undefined genetic metrics are displayed as undefined, not zero. No winner is preselected or inferred from a single interactive run.

## Manual catastrophe policy

Automatic random catastrophe probability is zero in live sessions; every accepted user intervention is recorded. The user chooses bottleneck, drought or combined effects and targets one environment or all. Parameters operate through the same catastrophe mechanism documented in `DISTURBANCE_PROTOCOL.md`. Shock mortality occurs at onset. Drought stock loss occurs once at onset and reduced renewal persists for the selected duration. A bottleneck's duration is an observation window, not repeated per-step killing.

Exactly one intervention can be active **globally**, including events targeting different environments. The next intervention must begin at least 8,000,000 displayed scenario years **after the previous intervention ends**. Both active duration and cooldown are rounded up to a whole computational update using decimal arithmetic, so coarse clocks may create longer intervals. First intervention is immediately available after start. End-of-horizon or global extinction can censor an active window. A scenario shorter than eight million displayed years may not have enough time for another event.

The policy is enforced under a backend lock, not only by disabling buttons. Double clicks/concurrent requests receive conflicts. While paused, an accepted event is reserved for the next update; another event is rejected. It executes only on resume. There is no event-count cap apart from the time horizon and spacing rule. Speed changes affect wall-clock pacing only. Model/gene/cost settings require a new session. Pausing does not advance time or cooldown. A lost UI heartbeat automatically pauses processing after 20 seconds; manual resume is required.

Inactive intervention effects are normalized explicitly: drought has zero direct mortality; bottlenecks have zero food loss and renewal multiplier one. The UI event list shows only mechanisms actually applied. The underlying drought-induced starvation, if any, remains a separate maintenance death. Detailed strategy inspection exposes all recorded observation metrics and cumulative reproductive, mortality, effort and resource counters; it is not restricted to the four headline columns.

## Survival and extinction display

Each strategy row displays its observed persistence from session start, in actual census updates and mapped million scenario-display years. Extinction uses the engine's first recorded zero census (`extinction_tick`), not the chart resolution or five-update metric sampling. Conversion is `extinction_tick * duration_million_years / steps`. Timing remains discrete to a census update and the scenario clock remains uncalibrated. The exact update is always shown even when the calendar label is rounded for display.

Living strategies display an ongoing status during active/paused runs and “alive at observation end” after completion/stop. Their duration is a lower bound (`≥`), not an invented extinction time; statistically these observations are right-censored. Early stops use the observed tick, not the full planned horizon. Empty observations without an extinction record are marked unknown. Detailed strategy inspection repeats these distinctions. A separate “export survival” CSV includes all environments, observed ticks/calendar durations, event-observed flags and blank extinction fields for living strategies, with an explicit uncalibrated-clock field. This is a descriptive per-session table, not a survival analysis across independent replicates.

Reconnecting/reloading the page restores the running server session's settings once, so its display-clock mapping is visible instead of the page's initial defaults. Later edits to prepare a new experiment do not change timing calculations for the currently observed session. This feature only reads the already recorded extinction events and does not change model behavior or restart the in-memory session.

## Persistence and reproducibility

The session runs in memory while active. Manual export and normal completion/stop save all environment checkpoints, metrics, per-step population/resource/catastrophe ledgers, founders and extinction events, plus a descriptive HTML report, history JSON and a versioned intervention manifest. Full per-offspring parentage is disabled to bound memory and is not advertised as retained. Browser reload reconnects to the same running server session; process crashes are not yet automatically recoverable from an active in-memory session.

`session.json` records initial settings, seeds, exact intervention update indices, requested durations, rounded windows and cooldowns, source/runtime signature and final state fingerprints. Fingerprints include population arrays, environment/parasite/onset arrays, resources, cumulative counters, current event parameters and RNG states. `replay_session` reproduces accepted events at the recorded update indices and checks the fingerprints, including pending paused interventions. Wall-clock pauses/speed changes are not biological randomness. Source and runtime must match. Old 0.2/0.3 results remain tied to their original preserved source copies.

Intervention selection is adaptive and user-driven. Results from a single live session are descriptive and cannot be treated as a preregistered unbiased comparison or independent replication. Exported data permit audit; confirmatory inference still requires separate frozen protocols, seeds, uncertainty and calibration.

## Local service boundaries

The HTTP service binds only to 127.0.0.1. Assets and fonts require no external network requests. Mutations require a per-server request token and same-origin/host checks. Only known asset routes and exports produced by this server can be downloaded; arbitrary filesystem traversal is rejected. No reports or GUI sessions are published automatically. Static assets and this protocol are included in source signatures, and packaged as ordinary project files.
