# Phase 09 — Root Cause Analysis: Review Package

**Phase objective (from the Phase 09 prompt):** implement reproducible
investigation of data issues and forecast discrepancies, including
root-cause analysis. Use only evidence supported by the dataset and clearly
separate association from causation.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–08 — see below. Several discrepancies come back
genuinely explained by available evidence; several honestly come back
unexplained. Both outcomes are reported as findings, not just the
flattering one.**

---

## Two investigation triggers, not invented here

This phase does not decide what counts as "worth investigating" — that was
already decided by earlier phases, which is exactly the "reproducible"
part of the objective:

1. **Data issues.** Phase 02's `rule_extreme_values` finding contains an
   explicit promise in its own `consequence` text: *"Phase 04 (demand
   analysis) and Phase 09 (RCA) investigate flagged points using business
   context — promotions, holidays, known events — before any modeling
   decision is made about them."* Phase 04 gathered that context
   (`extreme_value_context()`); this phase is the part that was
   deliberately deferred — turning the gathered context into an actual
   evidence-based conclusion.
2. **Forecast discrepancies.** CLAUDE.md §13: *"A forecast discrepancy or
   anomaly is an investigation trigger."* Phase 08 already found and
   structured 14 such triggers (its `weak_segment`, `systematic_bias`, and
   `segment_champion_switch` findings). This phase investigates *why* each
   one might be happening.

Both triggers are consumed, not recomputed from scratch — this phase's own
new work is the evidence-gathering and the evidence-based statement, not
re-deriving what already needed investigating.

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/rca/data_issue_evidence.py` (Part A) | `load_flagged_rows_with_context()` (returns/extreme-values with item family, store type, promotion, holiday), `load_baseline_rates()` (network-wide promotion/holiday rates, same exclusion rules as Phase 04's `promotion_effect()`), `gather_data_issue_evidence()`, `build_data_issue_rca()` — turns the gathered context into evidence-language statements, or an honest "cause unknown from available evidence" when nothing explains it. |
| `src/demandflow/rca/discrepancy_evidence.py` (Part B) | `rows_for_segment()` (reuses Phase 08's own `SEGMENT_KEY_FUNCTIONS` so segment membership here can never silently disagree with what Phase 08 reported), `unique_triples()` / `dq_flag_rates()` (see "a real bug" below), `segment_trend_slope()` / `network_trend_slope()` (reuses Phase 04's `trend_summary()`), `gather_discrepancy_evidence()`, `build_discrepancy_rca()`. |
| `src/demandflow/rca/run_rca.py` | Orchestrator. Runs Part A directly against the warehouse; for Part B, rebuilds Phase 08's evaluation itself (same "rebuild, don't trust a stale file" principle Phase 08 established) into a private `reports/phase09/_evaluation_rebuild/` copy, then investigates every `weak_segment` / `systematic_bias` / `segment_champion_switch` finding. |
| `src/demandflow/reporting/generate_rca_report.py` | Renders `docs/root_cause_analysis.md` — data issues, then forecast discrepancies grouped by (dimension, segment) so a segment flagged by two different Phase 08 findings isn't explained twice. |
| `src/demandflow/evaluation/segment_evaluation.py` (small additive refactor) | Exposed `SEGMENT_KEY_FUNCTIONS` (the per-dimension row-grouping lambdas Phase 08 already used internally) and added three DQ-flag columns to `load_scored_forecasts_with_context()`'s query, so Part B can reuse Phase 08's exact segment definitions and DQ context instead of re-deriving them. Verified behavior-preserving: all 29 Phase 08 tests re-run unchanged and passed before any Phase 09 code was written on top of it. |
| `tests/unit/test_data_issue_evidence.py`, `test_discrepancy_evidence.py`, `test_run_rca.py`, `test_generate_rca_report.py` | 35 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to 21 steps (20–21). New targets: `make rca`, `make rca-report`, `make phase09`. |

**Total test count: 208** (173 from Phases 01–08 + 35 new: 8 in
`test_data_issue_evidence.py`, 15 in `test_discrepancy_evidence.py`, 7 in
`test_run_rca.py`, 5 in `test_generate_rca_report.py`), all passing.

### A real bug, found and fixed while building this phase

The first version of Part B's DQ-flag-rate evidence computed rates
directly over Phase 08's `scored_rows` — but that list has one row per
**model**, not per underlying sales day: the same (store, item,
target_date) triple appears once for each of the 5 models scored against
it (or 4, when Seasonal Naive is skipped for a series with too little
history — the only one of the five with a hard history requirement). A DQ
flag belongs to the *day*, not to how many models happened to forecast it,
so computing a rate over the raw row list silently over- or under-weighted
triples depending on how many models reached them. On the first run this
inflated segment "n" counts (e.g. DAIRY showed n=164 instead of the true
31 distinct triples) and, because the duplication factor isn't uniform
(4 vs. 5), could have biased the computed rates themselves, not just the
displayed count. **Fixed by** adding `unique_triples()` — deduplicating by
`(store_nbr, item_nbr, target_date)` before computing any rate — and
routing both the per-segment and the network-wide baseline through it.
`test_dq_flag_rates_computed_over_distinct_triples_not_raw_rows` locks
this in: a triple duplicated 5x with one flag set must report rate 1.0 for
n=1, not a rate diluted or inflated by the duplication.

---

## The result — reported honestly, both explained and unexplained

### Part A: data issues (returns, extreme values)

Only 1 return row and 1 extreme-value row are flagged on this fixture —
too few to draw any conclusion, and the code says so rather than
manufacturing a pattern from n=1: *"cause unknown from available
evidence... the rates immediately below are shown for transparency, not
used to draw a conclusion."*

### Part B: forecast discrepancies (Phase 08's 14 findings)

| Segment | Evidence found | Verdict |
|---|---|---|
| `item_family=DAIRY` | Extreme-value rate 2.8x network baseline | **Associated with** extreme values |
| `item_family=GROCERY` | Demand trend diverges from network (−0.07 vs +0.73 units/day) | **Consistent with** a lag-based model missing a trend |
| `store_type=A`, `cluster=1` | Same trend divergence (same underlying stores) | **Consistent with** trend |
| `store_type=B`, `cluster=2` | Extreme-value rate ~2.3x baseline | **Associated with** extreme values |
| `promotion=not_promoted` (both findings) | Extreme-value rate ~4-5x baseline | **Associated with** extreme values |
| `holiday=non_holiday` | No elevated DQ rate, no trend divergence | **Cause unknown from available evidence** |
| `payday=non_payday`, `payday=payday` (both findings) | No elevated DQ rate, no trend divergence | **Cause unknown from available evidence** |
| `intermittency_class=intermittent` | Demand trend diverges (−0.38 vs +0.73) | **Consistent with** trend |
| `intermittency_class=lumpy` | Extreme-value rate 6.7x baseline | **Associated with** extreme values |

**9 of 14 triggers got a specific, evidence-backed candidate contributor
(extreme-value coincidence or trend divergence); 3 (holiday and both
payday-related findings) honestly came back "cause unknown from available
evidence."** This is the expected, correct shape of a real RCA exercise —
not every discrepancy has an explanation sitting in the dataset, and
CLAUDE.md §13 requires saying so plainly rather than reaching for a
plausible-sounding but unsupported story.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–08: no Kaggle network/credentials in
this sandbox. What's specific to this phase: the evidence-gathering
machinery (lift ratios, trend divergence, distinct-triple deduplication)
is proven correct here, but the *specific* verdicts above (which segments
are explained, which aren't) are fixture artifacts of a 20-day, ~10-item
history. The real ~4.6-year Favorita history would give every lift ratio
and every trend slope far more data to be estimated from, and could easily
flip which segments come back "explained" vs. "cause unknown."

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 208/208 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06
make phase07
make phase08
make phase09             # writes reports/phase09/, then docs/root_cause_analysis.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"Investigate data issues and forecast discrepancies, perform root-cause analysis"** — the phase's literal mission, addressed for both trigger types named in the objective | CLAUDE.md §3.6 |
| **"Do not automatically treat correlation as causation. Use evidence-based language"** — enforced by construction: `build_data_issue_rca()` / `build_discrepancy_rca()` are the *only* functions that write prose, and every sentence comes from a fixed template using "associated with" / "consistent with" / "cause unknown," never "caused by" | CLAUDE.md §13, and this phase's own objective line |
| **Reproducibility** — every RCA record is derived from a rerunnable query/computation against the warehouse, not a manually-written investigation note | CLAUDE.md engineering principles; this phase's objective: "reproducible investigation" |
| **Reused, not duplicated, prior phases' work** (Phase 04's flagged-row context and trend baseline, Phase 08's segment definitions and findings) | CLAUDE.md engineering principles: "modular code... maintainability" |
| **Fulfills a promise Phase 02's own code made** about what Phase 09 would do | Traceability across phases — the DQ rule catalog's `consequence`/`handling_decision` fields aren't just documentation, they're commitments this phase had to honor |

Not yet covered: monitoring over a real, longer history (Phase 10),
alerts/trackers (Phase 11), Airflow, BigQuery, dashboards.

---

## Key decisions

- **`horizon_decay` and `time_trend` findings are deliberately not
  re-investigated.** They describe a structural pattern across the whole
  horizon/as-of-date axis (not a specific segment), and Phase 08 already
  states their explanation in its own terms (a lag-based model's error
  grows with horizon; too few as-of dates for a robust trend). Forcing
  them through a "gather evidence for this segment" pipeline built for
  segment-shaped findings would mean fabricating a segment where none
  exists. Documented scope choice (CLAUDE.md §18), not an oversight.
- **Only R5 (returns) and R6 (extreme values) get Part A treatment** —
  the two Phase 02 rules that flag individual, inspectable rows. The other
  six describe structural/grain-level issues already handled by Phase
  02/03's documented decisions, or (missing calendar dates) explicitly
  routed to "the Phase 11 discrepancy tracker" by Phase 02's own text —
  not this phase's job to re-litigate.
- **Phase 08's evaluation is rebuilt, not read from a stale file** — same
  reproducibility principle Phase 08 itself established, applied one level
  up. Written to a private `_evaluation_rebuild/` subfolder so this
  phase's own output never overwrites Phase 08's report directory.
- **DQ-flag evidence is computed over distinct (store, item, target_date)
  triples, not raw scored-forecast rows** — the bug-fix above; this is now
  a named, tested function (`unique_triples()`) rather than an inline
  detail, so the same correctness applies everywhere it's used.
- **Trend-divergence evidence is only computed for the four "population"
  dimensions** (item family, store type, cluster, intermittency class) —
  a promotion/holiday/payday/horizon-step/as-of-date "segment" isn't a
  fixed set of items/stores with its own independent demand history, so
  "this segment's trend" isn't a meaningful question for those five;
  DQ-flag evidence (which only needs row-level flags) still applies to all
  eight.
- **Screening thresholds are named constants**
  (`ASSOCIATION_LIFT_THRESHOLD=1.5`, `MIN_EVIDENCE_N=5`,
  `TREND_DIVERGENCE_MAGNITUDE_RATIO=2.0`), labeled `[DECISION]` — the same
  heuristic-screen discipline as Phases 04 and 08, not JD figures.

## Validation

```
$ make test
........................................................................ [ 34%]
........................................................................ [ 69%]
................................................................         [100%]
208 passed in 78.32s

$ make smoke   # 21 steps, ending with the Phase 09 RCA + report
...
[20/21] Running the Phase 09 root-cause analysis (data issues + forecast discrepancies)
Rebuilding fct_forecast for evaluation: 2 as-of date(s) x 5 model(s)
Wrote .../reports/fixture_smoke_test/phase09/rca_summary.json:
2 data-issue record(s), 14 forecast-discrepancy record(s)
[21/21] Rendering the root cause analysis report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every table above is
copied verbatim from that real run, then cleaned up (`make clean-smoke`;
git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** 9 of 14 forecast-discrepancy triggers got a specific
  evidence-backed candidate contributor (extreme-value coincidence in 5
  segments; demand-trend divergence in 4); 3 (all holiday/payday-related)
  honestly came back "cause unknown from available evidence" — a genuine
  mixed result, not adjusted to look more conclusive.
- **The DQ-flag deduplication bug** (found before any test asserted
  against the buggy numbers) is the kind of thing that would have silently
  produced misleadingly precise-looking "n=164" counts in a generated
  report — caught by working out the underlying row-duplication mechanism
  by hand rather than trusting the first plausible-looking output.
- **Neither of the two flagged data-issue rows (1 return, 1 extreme value)
  has enough sample size to support a conclusion** — correctly reported as
  such rather than drawing one from n=1.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–08.
- **Every "cause unknown" verdict may simply reflect this dataset's own
  limits** (no stockout signal, no pricing, no external event calendar),
  not an exhaustive investigation — stated explicitly in the generated
  report's own Limitations section.
- **Small fixture samples limit Part A entirely** — 1 return, 1 extreme
  value; a real ~4.6-year history would give this part of the phase
  something substantive to work with.
- **All earlier phases' limitations still apply unchanged** (no pricing,
  store-as-hub proxy, Ecuadorian calendar, coarse transferred-holiday
  handling, unvalidated extreme-value fence at scale).

## What to review

1. **The DQ-flag deduplication fix** — confirm the reasoning (a DQ flag
   belongs to the day, not to how many models scored it) and that
   `unique_triples()` is applied everywhere a rate is computed in Part B.
2. **The three "cause unknown" verdicts** (holiday, payday×2) — confirm
   you're comfortable that this phase reports them as genuinely
   unexplained rather than stretching the trend/DQ evidence to manufacture
   a story for every trigger.
3. **The scope decision to exclude `horizon_decay`/`time_trend`** from
   re-investigation — confirm the reasoning holds (they're not
   segment-shaped, and Phase 08 already explains them).
4. **Run `make phase01` through `make phase09` locally** once Kaggle
   access exists — this phase's specific verdicts (which segments are
   "explained") are exactly the kind of result that could look very
   different with 4.6 years of real history instead of 20 days.

## Interview questions

- Walk through the DQ-flag deduplication bug: why did computing a rate
  over `scored_rows` directly produce a misleading number, and why isn't
  it just a display/cosmetic issue?
- Why are `horizon_decay` and `time_trend` findings deliberately not
  re-investigated in this phase, and what would go wrong if they were
  forced through the same segment-evidence pipeline as the others?
- What's the difference between this phase reporting "associated with
  extreme values" for DAIRY and reporting "extreme values caused DAIRY's
  forecast bias" — and where in the code is that distinction actually
  enforced, not just a matter of writing style?
- Three of fourteen triggers came back "cause unknown from available
  evidence." Is that a failure of this phase, or a correct outcome? Why?
- Why does Part B rebuild Phase 08's evaluation itself rather than reading
  `reports/phase08/evaluation_summary.json` directly?
- How would you extend Part A's business-context investigation if a real
  external event calendar (competitor promotions, local events) became
  available — what would change in `data_issue_evidence.py`, and what
  would stay the same?

---

**STOP — Phase 09 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 10 (Monitoring) has not started.
