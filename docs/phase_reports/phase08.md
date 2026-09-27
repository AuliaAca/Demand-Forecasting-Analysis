# Phase 08 — Forecast Evaluation: Review Package

**Phase objective (from the Phase 08 prompt):** implement rigorous
forecast-accuracy evaluation. Use appropriate metrics and segment analysis.
Connect results to the JD requirement to monitor forecast accuracy and
produce actionable findings.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–07 — see below. The fixture surfaces a genuine,
somewhat uncomfortable finding about the champion model (Seasonal Naive),
reported as-is, not softened.**

---

## What this phase is, and how it differs from what already existed

Phases 05–07 each already reported an *overall* WAPE/MAE/bias per model,
plus a couple of ad-hoc breakdowns (Phase 06's by-intermittency-class,
Phase 05/06's final-holdout and by-horizon-step). Those were explicitly
flagged in `backtest.py`'s own docstrings as "not Phase 08's full
accuracy-by-segment/horizon framework... a piece Phase 08 can reuse" —
i.e. this phase was scoped in advance, not invented after the fact.

Phase 04 analyzed **demand** across the JD's explicit dimensions (SKU, hub,
category, campaign, seasonal event — pricing excluded, no pricing data
exists in this dataset). Phase 08 asks the matching question for **forecast
accuracy**: not "what did demand look like across these dimensions" but
"where is the forecast right, and where is it weak" — directly the JD
mission "Monitor forecast accuracy and turn findings into actionable
recommendations" (CLAUDE.md Section 3.3).

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/evaluation/segment_evaluation.py` (new package) | Generic `evaluate_by_dimension()` (groups scored forecasts by any key, summarizes per model), 8 dimension-specific wrappers (item family, store type, cluster, promotion, holiday, payday, horizon step, as-of date), `champions_by_dimension()` (lowest-WAPE model per segment, with a minimum-sample-size floor), `accuracy_trend_by_model()` (OLS slope of WAPE across as-of dates — "is this getting worse over time"), and `identify_findings()`, which turns all of the above into a flat list of evidence-language findings across 4 categories: weak segments, systematic bias, segment-level champion switches, and horizon decay / time trend. |
| `src/demandflow/evaluation/run_evaluation.py` | Orchestrator. Rebuilds `fct_forecast` itself (same 5-model rolling-origin backtest as Phase 06: Naive, Seasonal Naive, SES, Croston, SBA), so this phase's evaluation is deterministic regardless of which backtest script last ran, rather than trusting whatever a previous phase happened to leave in the table. Joins the result with `dim_sku`, `dim_hub`, `fct_sales_daily`, and `int_calendar_by_store` for dimension context, then writes `reports/phase08/evaluation_summary.json`. |
| `src/demandflow/reporting/generate_evaluation_report.py` | Renders `docs/forecast_evaluation.md` — overall + per-dimension tables, horizon-decay table, as-of-date trend table, and a grouped findings/recommendations section, all computed from the summary JSON, never hand-typed. |
| `tests/unit/test_segment_evaluation.py`, `test_run_evaluation.py`, `test_generate_evaluation_report.py` | 29 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to 19 steps (18–19). New targets: `make evaluate`, `make evaluate-report`, `make phase08`. |

**Total test count: 173** (144 from Phases 01–07 + 29 new: 15 in
`test_segment_evaluation.py`, 8 in `test_run_evaluation.py`, 6 in
`test_generate_evaluation_report.py`), all passing.

### Why LightGBM (Phase 07) is not in this framework

Phase 07's ML model uses a deliberately different evaluation design: one
train/holdout split at the final as-of date, not a rolling-origin backtest
across every as-of date (documented in `docs/phase_reports/phase07.md` as
a cost/scope trade-off for a bonus phase). A model scored at exactly one
as-of date has nothing to show on an "accuracy over time" axis, and its
holdout rows are not independent draws from the same schedule the other
five models share. Folding it into the same per-segment/per-as-of-date
tables would either silently produce empty cells everywhere except one
column, or misrepresent a single-holdout number as if it had the same
statistical footing as a 2-as-of-date rolling backtest. This is a
documented scope decision (CLAUDE.md Section 18), not an oversight — the
evaluation report explains it and points to Phase 07's own result instead.

### The JD dimensions, mapped directly

| CLAUDE.md §3.1 dimension | How Phase 08 evaluates it |
|---|---|
| SKU | `intermittency_class` (reuses Phase 04's ADI/CV² classification) |
| Hub | `store_type`, `cluster` (both from `dim_hub`) |
| Category | `item_family` (from `dim_sku`) |
| Campaign | `promotion` (target-date `onpromotion_filled`, excluding rows with unknown promotion status) |
| Seasonal event | `holiday`, `payday` (from `int_calendar_by_store`) |
| Pricing | Not evaluated — no item-level pricing exists in this dataset, same limitation Phase 04 already documented (ADR 0001 D2). Not approximated. |

Plus two dimensions the JD dimensions don't name but forecast-accuracy
work specifically needs: **horizon step** (does error grow the further
ahead the forecast reaches?) and **as-of date / time** (is accuracy stable
across the backtest window, or drifting?).

---

## The result — reported honestly

### Overall (same 5-model rolling-origin backtest as Phase 06, reproduced identically)

| Model | n | WAPE | MAE | Bias |
|---|---|---|---|---|
| Naive | 105 | 1.073 | 2.648 | −62.5% |
| **Seasonal Naive** | 45 | **0.908** | 3.067 | −63.2% |
| SES | 105 | 1.204 | 2.970 | −36.4% |
| Croston | 105 | 1.453 | 3.584 | +8.6% |
| SBA | 105 | 1.421 | 3.504 | +3.2% |

Seasonal Naive is still the overall champion, exactly reproducing Phase
06's numbers (same computation — this is the cross-check that the
rebuild-fct_forecast design works correctly, not a coincidence).

### The genuinely useful finding: the champion's bias is not isolated

14 findings were generated on this fixture. 12 of them are the **same
finding recurring across 12 different segments**: Seasonal Naive
systematically *under*-forecasts — item family, store type, cluster,
promotion status, holiday status, payday status, and both intermittency
classes tested. Seasonal Naive's own **overall** bias is −63.2%, so this
is not 12 unrelated problems; it is one network-wide pattern showing up in
every slice, which the report calls out explicitly rather than listing 12
bullet points with no higher-level framing:

> Seasonal Naive's own overall bias is −63.2%, so this bias showing up
> across 12 different segments is consistent with a network-wide pattern,
> not several unrelated segment-specific issues.

This is a real, actionable finding for a demand-planning audience: **the
model that wins on WAPE is not necessarily safe to deploy unadjusted** —
consistently under-forecasting risks understocking and unmet demand at
scale, and that risk is invisible if WAPE is the only number reported
(exactly why CLAUDE.md §11 lists bias as its own metric, not a
nice-to-have alongside WAPE).

### The other two findings: segment-specific champion switches

| Segment | Better model | Its WAPE | Overall champion's WAPE in that segment |
|---|---|---|---|
| `promotion=not_promoted` | Croston | 0.746 | 0.843 (Seasonal Naive) |
| `payday=payday` | SES | 0.710 | 0.875 (Seasonal Naive) |

Both are stated as "associated with lower error," never "better," per
CLAUDE.md §13 — with only 45 scored Seasonal-Naive rows overall and single-
digit-to-low-double-digit segment sizes, this is suggestive, not proof
that either model should actually be swapped in for those slices on real
data.

### What did *not* trigger a finding

No `weak_segment` finding fired (no segment's champion-model WAPE exceeded
1.5× the overall WAPE for that model) and no `horizon_decay` finding fired
— the last horizon step (13) has only 1 scored row on this fixture, below
the 5-row screening minimum, so the comparison was correctly withheld
rather than drawn from a single point. Both are documented, not silently
absent.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–07: no Kaggle network/credentials in
this sandbox. Every number above is copied from an actual run in this
session. What's specific to this phase: the small sample sizes that make
several segment tables thin (some segments have as few as 1–8 scored
rows) are exactly the kind of thing a much longer, higher-volume real
history would resolve — the screening thresholds in
`segment_evaluation.py` exist specifically so that a segment too small to
say anything about is *not scored* rather than reported with false
confidence.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 173/173 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06
make phase07
make phase08             # writes reports/phase08/, then docs/forecast_evaluation.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Monitor forecast accuracy and turn findings into actionable recommendations** — the central mission this phase exists for | CLAUDE.md §3.3: "DemandFlow should therefore connect: forecast → evaluation → monitoring → finding → recommendation" |
| **Segment analysis across the JD's explicit demand dimensions**, applied to forecast error rather than demand volume — SKU (intermittency class), hub (store type, cluster), category (family), campaign (promotion), seasonal event (holiday, payday) | CLAUDE.md §3.1: "Analyze demand patterns across SKUs, hubs, categories, campaigns... and seasonal events" |
| **Appropriate metrics** (WAPE primary, MAE, forecast bias) used consistently, with the bias metric specifically surfacing a finding WAPE alone would have hidden | CLAUDE.md §11 |
| **Evidence-based language throughout** — "associated with," never "caused by" or "proves," including in the strongest finding (the network-wide bias pattern) | CLAUDE.md §13 |
| **Honest reporting of a systemic weakness in the current champion model**, not just a leaderboard | Requirements: "attention to detail," "turn complex analysis into clear business insights" |
| **Reused, not duplicated, existing building blocks** (`summarize_by_segment`, `summarize_backtest` from Phase 05/06) alongside genuinely new ones this phase owns | CLAUDE.md engineering principles: "modular code... maintainability" |

Not yet covered: root-cause analysis (Phase 09), monitoring / drift alerts
over a real, longer history (Phase 10), trackers/alerts (Phase 11),
Airflow, BigQuery, dashboards.

---

## Key decisions

- **`fct_forecast` is rebuilt by this phase itself**, not read as a
  side effect of whichever backtest script last ran. `run_evaluation.py`
  calls the exact same `build_extended_models` / `run_rolling_origin_backtest`
  Phase 06 uses, so evaluation is deterministic and reproducible standalone
  (`make phase08` doesn't require having just run `make phase06` first).
- **LightGBM is deliberately excluded from this framework** (see above) —
  a documented scope boundary, not a gap.
- **Promotion-unknown rows are excluded from the promotion breakdown**,
  not defaulted to "not promoted" — the same standard Phase 04's
  `promotion_effect()` already holds itself to, applied here to forecast
  rows instead of raw sales rows.
- **Screening thresholds are explicit, named constants**
  (`WEAK_SEGMENT_WAPE_RATIO=1.5`, `MIN_SEGMENT_SCORED_N=5`,
  `SYSTEMATIC_BIAS_THRESHOLD=0.20`), labeled `[DECISION]` in the module
  docstring — conventional heuristic screens in the same spirit as Phase
  04's ABC cutoffs and anomaly z-threshold, not JD figures, and not tuned
  to produce a particular headline finding.
- **The as-of-date trend is reported with an explicit "illustrative, not
  robust" caveat** rather than a confident slope, because this fixture's
  backtest schedule only produces 2 as-of dates — an OLS "trend" through 2
  points is not a trend estimate the report should imply is meaningful.
- **The report calls out the network-wide bias pattern explicitly** rather
  than only listing 12 individual segment bullets — the higher-level
  framing (one systemic issue, not 12 unrelated ones) is itself part of
  "turning findings into actionable recommendations," not just table
  output.

## Validation

```
$ make test
........................................................................ [ 41%]
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 57.87s

$ make smoke   # 19 steps, ending with the Phase 08 evaluation + report
...
[18/19] Running the Phase 08 forecast evaluation (segments, horizon, time, findings)
Rebuilding fct_forecast for evaluation: 2 as-of date(s) x 5 model(s)
Wrote .../reports/fixture_smoke_test/phase08/evaluation_summary.json:
champion model=seasonal_naive, 14 finding(s)
[19/19] Rendering the forecast evaluation report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every table above is
copied verbatim from that real run, then cleaned up (`make clean-smoke`;
git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** Seasonal Naive (the overall WAPE champion) shows a
  large, network-wide under-forecasting bias (−63.2% overall, recurring in
  12 of the segments tested) — a genuine result that complicates simply
  deploying "the lowest-WAPE model" without also checking its bias.
- **Two segment-specific champion switches** (Croston for
  `promotion=not_promoted`, SES for `payday=payday`) were found and
  reported with appropriately cautious language given small segment sizes.
- **No weak-segment or horizon-decay finding fired** on this fixture — both
  are documented as absent, with the specific reason (screening thresholds
  not crossed / insufficient sample at the longest horizon step), not
  silently omitted.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–07.
- **Small segment sizes on the fixture** — several segments have single-
  digit to low-double-digit scored rows; the `MIN_SEGMENT_SCORED_N`
  screening floor exists specifically to keep such segments from producing
  overconfident findings, at the cost of some segments (e.g. the longest
  horizon steps) having no finding reported at all.
- **The as-of-date trend has only 2 points on this fixture** — reported
  with an explicit caveat that this is illustrative, not a statistically
  meaningful drift estimate; the real ~4.6-year history would produce far
  more as-of dates.
- **Pricing remains unevaluated** — no pricing dimension exists in this
  dataset (unchanged from Phase 04).
- **All earlier phases' limitations still apply unchanged** (no stockout
  signal, store-as-hub proxy, Ecuadorian calendar, coarse
  transferred-holiday handling, unvalidated extreme-value fence at scale).

## What to review

1. **The network-wide bias framing** — confirm you're comfortable that the
   report leads with "the champion model under-forecasts almost
   everywhere" rather than burying it as one bullet among many; this is
   the phase's most consequential finding and it's about the model
   Phases 05/06/08 all currently call the "winner."
2. **The scope decision to exclude LightGBM** from this framework — confirm
   the reasoning (different evaluation design, no as-of-date breadth) is
   convincing, versus an alternative where Phase 08 also finds some way to
   fold in Phase 07's single-holdout result.
3. **The screening thresholds** (`WEAK_SEGMENT_WAPE_RATIO`,
   `MIN_SEGMENT_SCORED_N`, `SYSTEMATIC_BIAS_THRESHOLD`) — these are
   judgment calls, not JD figures; confirm they seem like reasonable,
   non-cherry-picked defaults rather than values chosen to produce a
   particular set of findings.
4. **Run `make phase01` through `make phase08` locally** once Kaggle
   access exists — the segment tables and the bias finding in particular
   are exactly the kind of result that could look different (or the same)
   at real scale, and this phase's honesty is only as good as the fixture
   it was validated against.

## Interview questions

- Walk through the difference between "Seasonal Naive has the lowest
  overall WAPE" and "Seasonal Naive is safe to deploy" — what did this
  phase find that complicates the second claim?
- Why is forecast bias reported as its own metric alongside WAPE, and what
  would you have missed here if you'd only looked at WAPE?
- Why does this phase rebuild `fct_forecast` itself rather than trusting
  whichever backtest script ran most recently?
- Why is Phase 07's LightGBM model deliberately not included in this
  evaluation framework, and what would go wrong if it were folded in
  naively?
- How would you distinguish "this segment's forecast error is genuinely
  worse" from "this segment just has too few scored rows to say anything
  yet" — and where in this phase's code is that distinction actually
  enforced?
- The as-of-date trend has only 2 points here. What would you need before
  you'd trust a "forecast accuracy is deteriorating over time" claim in a
  real monitoring system (Phase 10)?

---

**STOP — Phase 08 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 09 (Root Cause Analysis) has not started.
