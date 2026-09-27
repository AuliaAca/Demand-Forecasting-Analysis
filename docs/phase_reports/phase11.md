# Phase 11 — Alerts / Trackers: Review Package

**Phase objective (from the Phase 11 prompt):** implement actionable
alerts and/or trackers that support planning decisions. Include useful
evidence and severity, and avoid unnecessary alert noise.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–10 — see below. The key correctness property
this phase is judged on — a second, unchanged run producing zero alerts —
is verified with a real, hand-inspected double-run, not asserted from
theory.**

---

## Three explicit IOUs this phase closes

Nothing here was invented from a blank page — three earlier phases each
left an explicit, named promise for "Phase 11" in their own text, and this
phase's whole job is honoring them:

1. **Phase 02's `rule_missing_calendar_dates` finding:** *"Any unexplained
   gap is logged to the Phase 11 discrepancy tracker rather than silently
   zero-filled."*
2. **Phase 10's own review package:** *"logging results over time and
   raising an actual alert is Phase 11's job"* — Phase 10 deliberately
   computed a point-in-time status but never persisted it or compared it
   to anything.
3. **Phase 09's RCA:** 3 of its 14 forecast-discrepancy investigations
   ended "cause unknown from available evidence" — an investigation that
   ends without an answer needs somewhere to stay visible, not to vanish
   once Phase 09's report is generated.

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/alerts/history.py` | `record_snapshot()` appends Phase 10's monitoring signals to a `monitoring_history` table in the warehouse (`CREATE TABLE IF NOT EXISTS`, never `CREATE OR REPLACE` — the first table in this project meant to accumulate across runs, not be rebuilt fresh each time). `compute_alerts()` — pure, DB-free — fires an alert only when a signal's status differs from the immediately preceding recorded run; `load_recent_run_overall_statuses()` supports a run-history view. |
| `src/demandflow/alerts/tracker.py` | `calendar_gap_tracker_items()` (from Phase 02's `missing_calendar_dates` finding, resolving a gap automatically if it matches a documented non-trading day) and `discrepancy_rca_tracker_items()` (from Phase 09's "cause unknown" records, deduplicated by segment). `upsert_tracker_items()` updates an existing open item's `last_seen_at`/`times_seen` instead of inserting a duplicate on every run. |
| `src/demandflow/alerts/run_alerts.py` | Orchestrator. Reruns Phase 10's monitoring check and Phase 09's RCA fresh (same "rebuild, don't trust a stale file" principle established since Phase 08), then records/compares/upserts. |
| `src/demandflow/reporting/generate_alerts_report.py` | Renders `docs/alerts_and_tracker.md` — alerts table (or an explicit "no alert fired" statement), a run-history table, and the open-tracker table. |
| A small additive change to `src/demandflow/monitoring/signals.py` | Renamed `_SEVERITY_RANK` → `SEVERITY_RANK` (no behavior change) so this phase's alert-direction logic (escalated / de-escalated / recovered) reuses Phase 10's exact ranking instead of defining a second copy that could drift out of sync. Verified behavior-preserving: all 36 Phase 10 tests re-run unchanged and passed before any Phase 11 code was built on top of it. |
| `tests/unit/test_alerts_history.py`, `test_alerts_tracker.py`, `test_run_alerts.py`, `test_generate_alerts_report.py` | 35 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to 25 steps (24–25). New targets: `make alerts`, `make alerts-report`, `make phase11`. |

**Total test count: 279** (244 from Phases 01–10 + 35 new: 12 in
`test_alerts_history.py`, 11 in `test_alerts_tracker.py`, 7 in
`test_run_alerts.py`, 5 in `test_generate_alerts_report.py`), all passing.

### "Avoid unnecessary alert noise" — how it's actually enforced

Not a suppression rule bolted on afterward: `compute_alerts()` only
produces an alert record when `current_status != previous_status` for a
signal. An issue that stays BREACH across ten consecutive runs produces
**one** alert (when it first became BREACH) and then silence — the
tracker's `times_seen` counter is the mechanism for "this is still
happening," not a repeated alert. The same discipline applies to the
tracker: `upsert_tracker_items()` updates the existing row for an
already-open item rather than inserting a new one every run.

**Proven, not assumed:** the orchestrator was run twice against the same,
unchanged fixture warehouse in this session. Run 1 fired 2 alerts (new
BREACH for data quality, new WARN for anomalies — the two non-OK Phase 10
signals) and inserted 4 tracker items. Run 2, with nothing in the
underlying data changed, fired **zero** alerts and updated (not
duplicated) all 4 tracker items, bumping `times_seen` to 2. This exact
double-run is what `test_second_identical_run_fires_zero_alerts` and
`test_tracker_items_persist_and_increment_across_runs` check.

---

## The result — reported honestly

### Run 1 (first-ever recorded run on this fixture)

| Signal | Status | Alert fired? |
|---|---|---|
| Forecast accuracy | OK | No (clean first run — nothing new to report) |
| Forecast deterioration | OK | No |
| Data quality | BREACH | **Yes** — new, severity critical |
| Anomalies | WARN | **Yes** — new, severity warning |

### Discrepancy tracker (4 items, all opened on run 1)

| Category | Item | Severity | Status |
|---|---|---|---|
| calendar_gap | 2013-01-10 (no sales rows network-wide) | warning | open — does not match the known Dec 25 non-trading day |
| forecast_discrepancy | `holiday=non_holiday` | warning | open |
| forecast_discrepancy | `payday=non_payday` | warning | open |
| forecast_discrepancy | `payday=payday` | warning | open |

All three forecast-discrepancy items are exactly the three Phase 09
findings that came back "cause unknown" — nothing added, nothing
paraphrased away.

### Run 2 (unchanged warehouse)

Zero alerts fired. All 4 tracker items updated in place (`times_seen`
2 → confirmed, no duplicate rows). This is the phase's core deliverable
demonstrated, not just implemented.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–10: no Kaggle network/credentials in
this sandbox. What's specific to this phase: the persistence and
alert/tracker *logic* is proven correct via the double-run above; the
*specific* items in the tracker (one calendar gap, three "cause unknown"
discrepancies) are fixture artifacts and would very likely be a different
list — of a different size — on the real ~4.6-year dataset.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 279/279 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06
make phase07
make phase08
make phase09
make phase10
make phase11             # writes reports/phase11/, then docs/alerts_and_tracker.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"Build automated ... trackers, and alerts to make planning faster and smarter"** — this phase's literal mission | Position missions; CLAUDE.md §3.4 |
| **"Include useful evidence and severity"** — every alert carries the full underlying signal (`evidence`); every tracker item carries `severity`, `description`, and structured `evidence` | This phase's own objective line |
| **"Avoid unnecessary alert noise"** — enforced by construction (status-transition-only alerting, idempotent tracker upserts), verified by an actual double-run | This phase's own objective line |
| **"Investigate ... forecast discrepancies" carried through to resolution tracking** — Phase 09's unexplained findings don't disappear; they persist as open tracker items | CLAUDE.md §3.6, continued from Phase 09 |
| **Reused, not duplicated, four earlier phases' work** (Phase 02's DQ rule, Phase 04's non-trading-day research, Phase 09's RCA verdicts, Phase 10's signal ranking) | CLAUDE.md engineering principles |

Not yet covered: Airflow scheduling (Phase 12), BigQuery (Phase 13),
Looker Studio / dashboard (Phase 14), an actual outbound notification
channel (not part of this project's architecture at all — see Limitations).

---

## Key decisions

- **`monitoring_history` and `discrepancy_tracker` use `CREATE TABLE IF
  NOT EXISTS`, the only two tables in the whole project that do** — every
  other mart/table is `CREATE OR REPLACE` because it's meant to be rebuilt
  fresh each run; these two are explicitly meant to accumulate, which is
  the entire point of "persisted history" and "a tracker."
- **Alerts are derived at generation time from `monitoring_history`, not
  stored in a separate "alerts fired" table.** An alert is fully
  reconstructable from any two consecutive history rows, so persisting a
  second, redundant copy of the same information was judged unnecessary
  state (CLAUDE.md §9's cost principle) rather than added for its own sake.
- **A first-ever run does not alert on a clean (all-OK) result.** There is
  nothing new to report about a system that starts healthy; alerting on
  every signal on run 1 regardless of status would itself be the kind of
  noise the objective asks to avoid.
- **The discrepancy tracker's natural key is stable and content-based**
  (`calendar_gap:<date>`, `forecast_discrepancy:<dimension>:<segment>`),
  not a random ID — this is what makes the upsert idempotent across runs
  without needing to remember anything between processes beyond what's
  already in the warehouse.
- **No outbound notification (email/Slack/webhook) was built.** This
  project's architecture has no such channel, and building one only to
  have nothing real behind it would be infrastructure added "for
  appearance" (CLAUDE.md §18) rather than for demonstrated evidence.

## Validation

```
$ make test
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
...............................................................          [100%]
279 passed in 111.61s

$ make smoke   # 25 steps, ending with the Phase 11 alerts + tracker check + report
...
[24/25] Running the Phase 11 alerts + discrepancy tracker check
Wrote .../reports/fixture_smoke_test/phase11/alerts_and_tracker_summary.json:
run_seq=1, 2 alert(s), 4 open tracker item(s)
[25/25] Rendering the alerts & tracker report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every table above is
copied verbatim from that real run (including a manual second invocation
to verify the zero-alert behavior), then cleaned up (`make clean-smoke`;
git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** the first-ever run correctly surfaces the two
  genuinely non-OK Phase 10 signals as new alerts; an identical second run
  correctly produces none. Both are hand-verified via an actual double
  run, not just unit-tested in isolation.
- **The tracker correctly resolves a known non-trading day automatically**
  (tested with a synthetic Dec 25 date) while still opening a real,
  unexplained gap (2013-01-10 on this fixture) rather than resolving
  everything by default.
- **All three of Phase 09's "cause unknown" findings flow through to open
  tracker items, deduplicated correctly** where the same segment was named
  by more than one Phase 08 finding (`payday=payday`).

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–10.
- **The calendar-gap tracker only ever sees a sample** — Phase 02's
  `missing_dates_sample` is truncated to 20 dates; a real dataset with more
  gaps than that would only have a sample tracked here, not the complete
  list, which is an existing Phase 02 limitation this phase inherits
  rather than fixes.
- **The known-non-trading-day list is a single hard-coded entry (Dec 25)**
  from Phase 00's public-documentation research — a real gap the list
  doesn't recognize is (correctly, conservatively) left open rather than
  silently resolved, but the list itself is not exhaustive.
- **No outbound notification channel exists** — an alert here is a
  structured record in a JSON summary and a rendered report section, not
  an email or a Slack message; there is nothing in this project's
  architecture to send it to.
- **All earlier phases' limitations still apply unchanged** (no pricing,
  store-as-hub proxy, Ecuadorian calendar, coarse transferred-holiday
  handling, unvalidated extreme-value fence at scale, fixture-scale DQ
  severities from Phase 10).

## What to review

1. **The double-run proof** — confirm you're satisfied that
   `test_second_identical_run_fires_zero_alerts` and
   `test_tracker_items_persist_and_increment_across_runs` actually
   demonstrate the "avoid unnecessary alert noise" requirement, rather
   than just asserting it from the implementation.
2. **The two `CREATE TABLE IF NOT EXISTS` tables** — confirm this is the
   right (and only) place in the project's SQL/warehouse design where
   accumulating state across runs is appropriate.
3. **What counts as "cause unknown" flowing into the tracker** — confirm
   the string-matching approach (`"cause unknown from available evidence"
   in record["statement"]`) is an acceptable way to identify these, versus
   a more structured flag on Phase 09's RCA records.
4. **Run `make phase01` through `make phase11` locally** once Kaggle
   access exists — both the alert content and the tracker's specific open
   items are fixture-scale artifacts that would very likely look different
   at real scale.

## Interview questions

- Walk through why `monitoring_history` and `discrepancy_tracker` are the
  only two `CREATE TABLE IF NOT EXISTS` tables in the entire project,
  while everything else is `CREATE OR REPLACE`.
- What would happen to alert volume if `compute_alerts()` fired on every
  run a signal was non-OK, instead of only on a status transition — walk
  through a concrete 10-run scenario where a BREACH persists throughout.
- Why does a first-ever run not alert on an all-OK result, and why is that
  the correct behavior rather than a gap?
- How does the discrepancy tracker avoid creating a duplicate row every
  time the same underlying issue is detected again, and what is the
  natural key doing that a random UUID wouldn't?
- Why are Phase 09's "cause unknown" forecast discrepancies routed into
  this tracker instead of just staying in Phase 09's own report?
- If this project had a real Slack webhook or email service available,
  what would change in this phase's design, and what would stay exactly
  the same?

---

**STOP — Phase 11 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 12 (Airflow) has not started.
