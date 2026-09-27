# Phase 10 — Monitoring: Review Package

**Phase objective (from the Phase 10 prompt):** implement monitoring for
forecast accuracy, forecast deterioration, data quality, anomalies, and
other signals justified by the project. Connect monitoring to the JD's
requirement for automated monitoring.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–09 — see below. The fixture's overall status
comes back BREACH, driven by data quality — reported as-is, not tuned to
look green.**

---

## What Phase 10 adds that Phases 02–09 didn't have

Every number this phase uses was already computable before this phase
existed: Phase 02's DQ rule severities, Phase 04's network-anomaly
z-scores, Phase 05/06's backtest WAPE. What none of it did was turn a
number into an automated **verdict** — a status level, judged against an
explicit threshold, that a pipeline or a human could act on without
re-reading a report. That is this phase's entire contribution: four signal
functions, each taking numbers Phases 02–06 already compute and returning
one of **OK / WARN / BREACH / UNKNOWN** plus the reason.

### Scope boundary: Monitoring (10) vs. Alerts / Trackers (11)

The project's own phase list separates these. This phase answers *"what is
the status right now, and why"* for one point-in-time run. It does **not**:
- persist a history of snapshots (so "3 breaches in a row" can be
  detected) — the whole reason "forecast deterioration" gets its own
  signal here is to answer part of that question *without* needing
  persisted history, by comparing the final holdout against pooled prior
  periods within a single backtest run;
- decide who gets notified or write to any external channel;
- write anything to `fct_forecast` — the accuracy/deterioration signals
  only need the backtest's in-memory records, so, unlike Phases 08–09,
  this phase never mutates the warehouse.

Those are explicitly Phase 11's job. Documented scope choice (CLAUDE.md
§18), not a partial implementation.

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/monitoring/signals.py` | Four signal functions, each pure and independently testable: `forecast_accuracy_signal()` (is the champion model's overall WAPE within an acceptable range at all), `forecast_deterioration_signal()` (is the most recent as-of date's WAPE much worse than the pooled WAPE across earlier as-of dates), `data_quality_signal()` (rolls up Phase 02's 8 rule severities to one status), `anomaly_signal()` (restricts Phase 04's z-score anomaly screen to a recent look-back window). Plus `overall_status()` — the worst-of-all-signals rollup, with `UNKNOWN` deliberately ranked above `OK` so a signal that couldn't be computed is never silently treated as healthy. |
| `src/demandflow/monitoring/run_monitoring.py` | Orchestrator. Reruns Phase 02's DQ rules fresh against the current parquet files, Phase 04's anomaly screen fresh against the warehouse, and a fresh 5-model rolling-origin backtest (same "rebuild, don't trust a stale file" principle Phases 08–09 established) — then classifies all four signals and writes one snapshot. |
| `src/demandflow/reporting/generate_monitoring_report.py` | Renders `docs/monitoring.md` — overall status table, one section per signal with its full detail, generated from the JSON, never hand-typed. |
| `tests/unit/test_monitoring_signals.py`, `test_run_monitoring.py`, `test_generate_monitoring_report.py` | 36 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to 23 steps (22–23). New targets: `make monitor`, `make monitor-report`, `make phase10`. |

**Total test count: 244** (208 from Phases 01–09 + 36 new: 23 in
`test_monitoring_signals.py`, 7 in `test_run_monitoring.py`, 6 in
`test_generate_monitoring_report.py`), all passing.

### The four signals, and why each threshold is what it is

| Signal | What it checks | Threshold | Why |
|---|---|---|---|
| Forecast accuracy | Champion model's overall WAPE | WARN ≥ 1.0, BREACH ≥ 1.5 | WAPE ≥ 1.0 means total absolute error is at least as large as total actual volume — a scale-free "this forecast is no better than predicting near-zero" line. 1.5 means the error actively exceeds volume by half again. Both `[DECISION]`, not JD figures — the same style as Phase 04's ABC cutoffs. |
| Forecast deterioration | Final-holdout WAPE ÷ pooled prior-periods WAPE, same model | WARN ≥ 1.2×, BREACH ≥ 1.5× | The same relative-lift-ratio pattern already used by Phase 08's `WEAK_SEGMENT_WAPE_RATIO` and Phase 09's `ASSOCIATION_LIFT_THRESHOLD`, applied to accuracy over time instead of accuracy across a segment. |
| Data quality | Worst severity across Phase 02's 8 rules | PASS/INFO/LOW→OK, MEDIUM→WARN, HIGH/CRITICAL→BREACH | A rollup of severities Phase 02 already justified per-rule — this phase only decides which of those severities should stop a pipeline run. |
| Anomalies | Count of Phase 04's z-score anomalies in the last 7 days | WARN ≥ 1, BREACH ≥ 2 | 7 days reuses the project's existing `season_length_days` convention rather than introducing an unrelated number; anomaly *detection* itself is untouched Phase 04 logic. |

No additional "other signals justified by the project" were added. The
four named in the objective already draw on everything the pipeline
produces that has a natural pass/fail shape (a rule severity, a z-score
screen, a WAPE number, a WAPE-over-time comparison); adding more without a
genuinely new underlying computation would be manufacturing signals for
appearance, which CLAUDE.md §9/§18 explicitly warn against.

---

## The result — reported honestly

On this fixture:

| Signal | Status | Why |
|---|---|---|
| Forecast accuracy | **OK** | Seasonal Naive's overall WAPE is 0.908 — below the 1.0 WARN line. |
| Forecast deterioration | **OK** | Final holdout (2013-01-14) WAPE 0.906 vs. prior-period WAPE 0.913 — a ratio of 0.99×, i.e. slightly *better*, not worse. |
| Data quality | **BREACH** | `grain_duplicates` and `orphan_dimension_keys` are both HIGH severity on this fixture. |
| Anomalies | **WARN** | 1 network-wide anomaly (z=4.14 on 2013-01-20) inside the most recent 7-day window. |
| **Overall** | **BREACH** | The worst of the four. |

**This is reported as a real BREACH, not softened.** It would be easy to
frame this phase's headline result around the two green forecast signals;
instead the overall status — which is what an automated system or a
person skimming this report would actually see first — is BREACH, driven
by data quality, exactly as the worst-of-all-signals rule requires.

That said, the specific BREACH here is a **fixture artifact, explicitly
flagged as such**: on a 52-row fixture, 1 duplicate key group and 1 orphan
row are enough to look severe in percentage terms, and Phase 02's own
severity rules (written before this fixture existed, calibrated for
real-scale reasoning) mark any duplicate or orphan row as HIGH regardless
of scale. The monitoring *machinery* — the thresholds, the rollup logic,
the worst-of rule — is proven correct here; whether the real ~4.6-year
dataset would also breach is a separate, real question this fixture cannot
answer (see Limitations).

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–09: no Kaggle network/credentials in
this sandbox. What's specific to this phase: the BREACH above is likely a
fixture-scale artifact rather than a real finding (see above) — this
phase's job was to prove the monitoring logic reacts correctly to real
underlying findings, which it does (a real HIGH-severity DQ rule *should*
breach an automated check), not to claim the real dataset breaches too.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 244/244 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06
make phase07
make phase08
make phase09
make phase10             # writes reports/phase10/, then docs/monitoring.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"Monitor forecast accuracy"** — turned from a report you have to read into an automated status | Position purpose; CLAUDE.md §3.3 |
| **Automated monitoring, connected to prior phases' outputs rather than re-detecting from scratch** | This phase's own objective line: "Connect monitoring to the JD's requirement for automated monitoring" |
| **"Where is forecast accuracy deteriorating?"** — answered per-run via the deterioration signal, not left as an open question | CLAUDE.md §7 business questions |
| **Data quality treated as an ongoing operational concern, not a one-time Phase 02 report** | CLAUDE.md §12; this phase's objective: "monitoring for ... data quality" |
| **Anomaly monitoring connected to a concrete recency window**, not a static one-time finding | This phase's objective: "monitoring for ... anomalies" |
| **Reused, not duplicated, four earlier phases' detection logic** (Phase 02 rules, Phase 04 anomalies, Phase 05/06 backtest) | CLAUDE.md engineering principles: "modular code... maintainability" |

Not yet covered: persisted history / alerting (Phase 11), Airflow
scheduling (Phase 12), BigQuery (Phase 13), dashboards (Phase 14).

---

## Key decisions

- **No history is persisted.** A monitoring snapshot from this phase is a
  single point-in-time verdict; running it again overwrites the file.
  Tracking trend-over-multiple-runs and turning a BREACH into an actual
  alert are Phase 11's explicit job, per the project's own phase list.
- **`fct_forecast` is never written by this phase** — a deliberate
  departure from Phase 08/09's pattern, since monitoring's accuracy/
  deterioration signals only need the backtest's in-memory records; there
  is no reason for a read-only health check to mutate the warehouse.
- **The deterioration signal is a within-run comparison** (final holdout
  vs. pooled prior periods), not a cross-run one — this sidesteps needing
  persisted history to answer "is this getting worse" at all, at the cost
  of being less statistically robust with only a couple of as-of dates
  (documented in Limitations).
- **All four thresholds are named, documented `[DECISION]` constants** in
  `signals.py` — the same heuristic-screen discipline as every prior
  phase's thresholds (Phase 04's ABC cutoffs and z-threshold, Phase 08's
  weak-segment ratio, Phase 09's association-lift threshold).
- **No signals were added beyond the four the objective names.** Checked
  against CLAUDE.md §9's cost principle and §18's "don't add infrastructure
  only for appearance" — everything with a natural pass/fail shape is
  already covered by the four; nothing else in the pipeline currently
  produces a number that would support a fifth signal without inventing
  one for its own sake.

## Validation

```
$ make test
........................................................................ [ 29%]
........................................................................ [ 59%]
........................................................................ [ 88%]
............................                                             [100%]
244 passed in 83.48s

$ make smoke   # 23 steps, ending with the Phase 10 monitoring check + report
...
[22/23] Running the Phase 10 monitoring check (accuracy, deterioration, DQ, anomalies)
Wrote .../reports/fixture_smoke_test/phase10/monitoring_snapshot.json:
overall_status=BREACH (forecast_accuracy=OK, forecast_deterioration=OK,
data_quality=BREACH, anomalies=WARN)
[23/23] Rendering the monitoring report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every table above is
copied verbatim from that real run, then cleaned up (`make clean-smoke`;
git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** overall status is BREACH, driven entirely by data
  quality (`grain_duplicates`, `orphan_dimension_keys` — both known,
  already-documented Phase 02 findings, not new discoveries). Forecast
  accuracy and forecast deterioration are both OK; the single anomaly
  signal is WARN.
- **The forecast-deterioration signal correctly reports "not enough
  history" as UNKNOWN when fewer than 2 as-of dates have scored
  forecasts** — verified via a dedicated test rather than assumed.
- **The DQ rollup surfaces exactly the rules driving the worst status**
  (`driving_rules`), not just the aggregate severity, so an operator (or a
  future Phase 11 alert) knows what to look at first.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–09.
- **The fixture's DQ BREACH is very likely a small-sample artifact** — 1
  duplicate key group and 1 orphan row on 52 total rows read as HIGH
  severity under Phase 02's own (already-justified) rules; the same
  absolute counts would very likely register differently at real-dataset
  scale. This phase does not know which way the real dataset would go —
  documented as an open question, not assumed either way.
- **The deterioration signal has very little data to work with here** —
  only 2 as-of dates on this fixture, so the "OK" verdict rests on
  comparing 1 final-holdout period against exactly 1 prior period, far
  short of the robustness a real, longer backtest history would provide.
- **All earlier phases' limitations still apply unchanged** (no pricing,
  store-as-hub proxy, Ecuadorian calendar, coarse transferred-holiday
  handling, unvalidated extreme-value fence at scale).

## What to review

1. **The overall BREACH status and its DQ-scale caveat** — confirm you're
   comfortable this phase reports the real (if fixture-driven) BREACH
   rather than quietly excluding data quality from the rollup to present
   a cleaner headline.
2. **The four thresholds** (`FORECAST_ACCURACY_WAPE_WARN/BREACH`,
   `DETERIORATION_WARN/BREACH_RATIO`, the DQ severity mapping, the 7-day
   anomaly window) — confirm they read as reasonable, non-arbitrary
   defaults, not values tuned to produce a particular headline.
3. **The Phase 10 / Phase 11 scope boundary** — confirm the reasoning for
   what's deliberately deferred (persisted history, notifications) holds
   up, and that nothing here quietly does part of Phase 11's job or
   nothing Phase 11 will need is missing here.
4. **Run `make phase01` through `make phase10` locally** once Kaggle
   access exists — the DQ signal in particular is the one most likely to
   read differently at real scale.

## Interview questions

- Why does the overall status roll up to BREACH here even though two of
  the four signals are OK — walk through the worst-of-all-signals logic
  and why `UNKNOWN` is ranked above `OK` rather than being ignored.
- Why is the DQ BREACH on this fixture not necessarily meaningful for the
  real dataset, and what would you need to see on real data before
  trusting this signal's verdict there?
- Why does the forecast-deterioration signal compare a final holdout
  against *pooled* prior periods rather than, say, the single previous
  as-of date — what would break with fewer as-of dates if it compared
  against just one?
- What is the difference in responsibility between this phase and Phase
  11 (Alerts / Trackers), and why does that split make sense rather than
  building persistence and notification here too?
- Why doesn't this phase write to `fct_forecast`, unlike Phase 08 and
  Phase 09?
- If you had to add a fifth monitoring signal, what would it be, and what
  underlying computation (not yet a pass/fail check) would it need to
  build on?

---

**STOP — Phase 10 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 11 (Alerts / Trackers) has not started.
