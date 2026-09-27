# Phase 04 — Exploratory Demand Analysis: Review Package

**Phase objective (from the Phase 04 prompt):** analyze demand patterns using
only dimensions available in the selected dataset. Prioritize the JD's SKU,
hub/store, category, campaign, pricing, and seasonal-event dimensions when
supported. Analyze trends, seasonality, outliers, and demand anomalies.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–03 — see below.** Pricing was **not** analyzed —
no pricing data exists in this dataset (ADR 0001 D2); the report says so
explicitly rather than silently omitting the section.

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/analysis/eda.py` | 8 analysis functions against the Phase 03 warehouse: SKU velocity/ABC/intermittency, hub summary, category summary, promotion effect, seasonal-event effect (holiday/day-of-week/payday), trend, extreme-value business context, network-wide anomalies. |
| `src/demandflow/analysis/charts.py` | 4 matplotlib charts (daily trend, day-of-week, promotion uplift, holiday effect), styled from this project's dataviz skill's validated palette and mark specs — loaded and read before writing any chart code, per its trigger. |
| `src/demandflow/analysis/run_eda.py` | Orchestrates the above against an already-built warehouse; writes `reports/phase04/eda_summary.json` and the chart PNGs. |
| `src/demandflow/reporting/generate_eda_report.py` | Renders `docs/eda_findings.md` from the summary JSON — generated, never hand-typed, same principle as every prior phase. |
| `tests/unit/test_eda.py`, `test_charts.py`, `test_generate_eda_report.py` | 25 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended with steps 10–11 (run EDA, render report). New targets: `make eda`, `make eda-report`, `make phase04`. |

**Total test count: 71** (50 from Phases 01–03 + 21 new: 13 in `test_eda.py`, 4 in `test_charts.py`, 4 in `test_generate_eda_report.py`), all passing.

### Dimension coverage this phase actually delivers

| JD dimension | Covered? | What was built |
|---|---|---|
| SKUs | Yes | ABC classification (cumulative volume share) + Syntetos-Boylan-Croston intermittency classification (smooth/intermittent/erratic/lumpy) per item |
| Hubs (stores) | Yes (proxy, ADR 0001 A1) | Total/avg demand and distinct-item count per store |
| Categories | Yes | Total/avg demand by family, perishable split |
| Campaigns (promotion) | Yes | Promoted vs. not-promoted average, with unknown-promotion and return rows explicitly excluded from the comparison (not silently blended in) |
| Seasonal events | Yes | Holiday effect (resolved per store's locale, from Phase 03's calendar), day-of-week, payday |
| Pricing | **No — documented, not fabricated** | A dedicated report section states plainly why, citing ADR 0001 D2 |
| Trends | Yes | Network-wide daily total, rolling mean, OLS slope + direction |
| Seasonality | Yes | Day-of-week and holiday breakdowns (see above) |
| Outliers | Yes | Phase 02/03's `is_return`/`is_extreme_value` flags cross-referenced with promotion and holiday context — the "investigate flagged points using business context" step Phase 02 explicitly deferred to here |
| Demand anomalies | Yes | A separate, network-wide day-level z-score screen (distinct from Phase 02's per-row IQR fence) |

---

## A genuine, honest finding the fixture itself surfaced

This is worth calling out directly rather than folding into "Findings" below:
on this 52-row fixture, the single planted extreme value (item 104, store 2,
80 units on 2013-01-20, not promoted, not a holiday) **by itself** produces
several misleading-looking "effects" if read naively:

- Promotion "uplift" comes out **negative** (-19.5%) — because that
  unpromoted 80-unit row inflates the *not-promoted* average.
- Holidays appear to show **lower** average sales than non-holidays — same
  mechanism, different slice.
- Sunday appears to have by far the highest day-of-week average (12.94 vs.
  2.5–4.1 for every other day) — because 2013-01-20 is a Sunday.
- The trend line shows a sharp upward slope, driven almost entirely by that
  one day.

None of this is a bug — it is exactly what a coarse aggregate does with 52
rows and one large flagged value in them. The `extreme_value_context`
function exists specifically to catch this: it shows the point coincides
with **no** promotion and **no** holiday, so the honest read is "an
unexplained flagged value materially shapes every aggregate view on this
small sample" — not "promotions and holidays reduce demand." This is a
genuine demonstration of exactly the caution CLAUDE.md §13 asks for
(evidence-based language, no unsupported causal claims), and it is a fixture
artifact, not a claim about the real dataset. See `docs/eda_findings.md`
(once generated from a real run) for whether this pattern holds at scale.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–03: no Kaggle network/credentials in this
sandbox. Every function was run for real against the fixture warehouse in
this session — all numbers above are copied from an actual run, hand-checked
against the fixture's known contents (e.g., item 104's total of 86.0 units,
store 2's total of 108.5) — not just "the code executed without error."

What's genuinely new here, beyond the general real-vs-fixture gap: **EDA
findings are the most sample-size-sensitive output in the whole pipeline so
far.** Phases 01–03 mostly validate mechanism (does the dedup logic work,
does the dense grid fill correctly) — those conclusions transfer to real
data unchanged. Phase 04's *findings* (promotion uplift, holiday effect,
trend direction) are numbers that will look completely different, and be
far more statistically meaningful, on ~4.6 years and thousands of items than
on 20 days and 10 items. The fixture demonstrates the analysis is *correct*;
it says nothing about what the real analysis will *find*.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 71/71 pass on this machine too
make phase01
make phase02
make phase03
make phase04            # writes reports/phase04/, then docs/eda_findings.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Analyzing demand patterns across SKUs, hubs, categories, campaigns, and seasonal events** | Missions: "Analyze demand patterns across SKUs, hubs, categories, campaigns, pricing, and seasonal events" (5 of 6; pricing explicitly undemonstrated, documented) |
| **Trends, seasonality, outliers, and demand anomalies** | Missions: "identifying trends, seasonality, outliers, and demand anomalies" — all four implemented as distinct, named functions, not folded together |
| **Investigating flagged points with business context**, continuing Phase 02's explicit hand-off | Missions: "Investigate data issues... perform root-cause analysis" (full RCA is Phase 09; this phase does the context cross-reference Phase 02 deferred here) |
| **Turning complex analysis into clear business insights** — the fixture-driven-outlier finding above is exactly this kind of insight | Requirements: "Able to turn complex analysis into clear business insights and recommendations" |
| **Evidence-based language**, never asserting causation from correlation | CLAUDE.md §13; enforced in the generated report's own wording, and tested (`test_render_eda_report_never_asserts_causation_for_flagged_points`) |

Not yet covered: forecasting, evaluation, monitoring, dashboards, alerts,
BigQuery, RCA (Phase 09), recommendations log (Phase 09–11).

---

## Key decisions

- **Intermittency classification uses the conventional Syntetos-Boylan-
  Croston thresholds** (ADI ≥ 1.32, CV² ≥ 0.49) — `[DECISION]`, a standard
  from the intermittent-demand literature, not a JD figure. Directly informs
  Phase 05+'s choice of forecasting method per series (e.g., Croston/TSB for
  intermittent/lumpy series vs. standard methods for smooth ones).
- **Promotion and seasonal-event comparisons use `stg_sales` (real observed
  rows), not the dense `fct_sales_daily` table.** The dense table's
  `onpromotion_filled` defaults imputed/unknown days to `False`, which would
  silently blend "confirmed not promoted" with "unknown" and with "no real
  observation at all" into one bucket — exactly the kind of silent
  conflation CLAUDE.md's data-quality principles warn against. Unknown-
  promotion and return rows are excluded from the comparison explicitly and
  their exclusion counts are reported, not hidden.
- **Network-wide anomaly detection is a separate, coarser screen** from
  Phase 02's per-row IQR fence — a day-level z-score over the whole series,
  `[DECISION]` threshold 2.0 standard deviations, not a JD figure.
- **The daily-trend chart uses real `datetime.date` objects**, not date
  strings, specifically so matplotlib treats the x-axis as a time axis
  rather than categorical labels — a small but real correctness/attention-
  to-detail fix made during this phase (the initial version triggered a
  matplotlib warning; fixed rather than ignored).
- **Charts follow this project's dataviz skill**, loaded before writing any
  chart code per its trigger: fixed-order categorical hues (blue for the
  primary series, orange only when a second series — the rolling mean —
  needs its own identity), no dual-axis charts, a legend only when ≥2
  series, hairline recessive gridlines, text in ink tokens rather than data
  color.

## Validation

```
$ make test
.......................................................................  [100%]
71 passed in 9.39s

$ make smoke   # 11 steps, ending with EDA + report generation
...
[10/11] Running the Phase 04 exploratory demand analysis
       wrote reports/fixture_smoke_test/phase04/eda_summary.json and 4 chart(s)
[11/11] Rendering the EDA findings report (fixture preview — NOT the real findings)
       wrote reports/fixture_smoke_test/eda_findings_PREVIEW.md
Smoke test complete.
```

Both commands were actually run in this session; the fixture-driven-outlier
finding above and every number in it are copied from that real run, then
cleaned up (`make clean-smoke`; git-ignored anyway). Charts were visually
inspected (not just size-checked) before being accepted.

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** every number reported above is hand-verified, and the
  single most important one is the outlier-driven-effects observation
  above — a genuine illustration of why small-sample EDA results need
  exactly this kind of cross-referencing before they're trusted.
- Item 104 (DAIRY) is the top-volume item in the development scope and is
  classified `lumpy` (high ADI, high CV²) — consistent with its volume
  being dominated by one very large, otherwise-unexplained observation
  rather than steady demand.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–03.
- **Every fixture-derived number in this document is a mechanism proof,
  not a finding about Favorita.** Stated repeatedly above because it is the
  single most important caveat for this phase specifically.
- **`docs/eda_findings.md` does not yet exist** — same honesty reason as
  every previous phase's generated document. `make phase04` produces it
  from a real run.
- **The network-anomaly screen is whole-series, not per-segment** — a real
  anomaly local to one store or family could be diluted by the network-wide
  aggregate. Worth revisiting once real data shows whether this matters.
- **All Phase 00–03 limitations still apply unchanged** (no pricing, no
  stockout signal, store-as-hub proxy, Ecuadorian calendar, transferred-
  holiday semantics simplified).

## What to review

1. **`docs/eda_findings.md`'s "Outliers and demand anomalies" section**
   (once generated) — confirm the language never tips into asserting
   causation; this was explicitly tested but worth your own read.
2. **The Syntetos-Boylan-Croston thresholds** in `eda.py` — standard
   literature values; flag now if you'd rather use different ones before
   Phase 05+ starts relying on this classification for method choice.
3. **The promotion/seasonal-effect exclusion logic** (unknown-promotion and
   return rows excluded, counts reported) — confirm this is the comparison
   you want, versus including them with appropriate weighting.
4. **Run `make phase01 && make phase02 && make phase03 && make phase04`
   locally** once Kaggle access exists, and look at whether the real
   findings (promotion uplift, holiday effect, trend) look statistically
   sane at scale — this is the first phase where "sane at scale" is itself
   the main open question.

## Interview questions

- Walk through the fixture's outlier-driven-effects finding — why does one
  data point make promotion uplift look negative, and what would you check
  before trusting a promotion-effect number on a real, larger dataset?
- Why does the promotion-effect comparison use `stg_sales` instead of the
  dense `fct_sales_daily` table you built in Phase 03?
- What's the difference between the Phase 02 IQR-based extreme-value flag
  and the Phase 04 network-wide anomaly z-score — why have both?
- Why does the SKU analysis use ADI and CV² instead of, say, just ranking
  items by total volume?
- The report states "no explanation was found" for the flagged points
  rather than "these are errors" — why does that distinction matter, and
  where does CLAUDE.md require it?
- If Phase 04's findings on the real dataset contradicted what the fixture
  showed, what would that tell you, and what wouldn't it tell you?

---

**STOP — Phase 04 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 05 (Forecast Baselines) has not started.
