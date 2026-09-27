# Phase 06 — Statistical Models: Review Package

**Phase objective (from the Phase 06 prompt):** implement and evaluate
statistical forecasting only if justified by the data and baseline results.
The JD does not prescribe a specific algorithm, so document the reason for
the choice.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–05 — see below. The honest result on this
fixture is a mixed/negative one, reported as such, not adjusted to look
better.**

---

## The justification (required before any code, per the phase objective)

1. **Phase 04's SKU analysis** classified most development-scope items as
   intermittent or lumpy — many zero-demand days, high demand-size
   variability (Syntetos-Boylan-Croston thresholds).
2. **Phase 05's baselines** showed WAPE at or above 1.0 on these series —
   both Naive and Seasonal Naive already struggle here.
3. **Croston's method (1972) and its bias-corrected variant SBA
   (Syntetos & Boylan, 2005)** exist specifically for this data pattern:
   they smooth nonzero demand *size* and the *interval between* nonzero
   observations separately, rather than smoothing the raw (mostly-zero)
   series the way generic exponential smoothing does.

This is the chain of evidence the phase objective asks for: not "the JD
mentions statistical models," but "the data is intermittent, baselines
already struggle on it, and a specific, well-established method family
exists for exactly that pattern." Generic ETS/ARIMA were **not** attempted
— those assume continuous, non-intermittent demand, which Phase 04 already
found does not describe most of this development scope, and the fixture's
series are in any case too short (≤20 observations) for those methods to
fit meaningfully.

**SES (Simple Exponential Smoothing) was included too — deliberately, as
the comparison point for the failure mode being addressed**, not because
it was expected to win: it smooths one level across zero and nonzero
periods alike, which is exactly what Croston's method exists to avoid.

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/forecasting/statistical.py` | `ses_forecast`, `croston_forecast` (with a `variant="sba"` bias correction) — hand-implemented, no new dependency (no mainstream Python library implements Croston natively; this is the ordinary way it's done). |
| `src/demandflow/forecasting/backtest.py` (refactored) | `run_rolling_origin_backtest` now takes a pluggable `models: dict[str, ForecastFn]` instead of hardcoding Naive/Seasonal Naive — reused by Phase 06 rather than forked, so the leakage-critical slicing logic exists in exactly one place. `default_models()` preserves Phase 05's exact call signature (`season_length=`) for backward compatibility. New: `summarize_by_segment`, a generic per-item-label breakdown (used here for intermittency class; reusable by Phase 08 for other segment definitions). |
| `src/demandflow/forecasting/run_statistical_backtest.py` | Runs all 5 models (Naive, Seasonal Naive, SES, Croston, SBA) through the same backtest, loads the extended result into `fct_forecast` (superseding Phase 05's 2-model version in the same table), and computes the by-intermittency-class breakdown. |
| `src/demandflow/reporting/generate_statistical_models_report.py` | Renders `docs/statistical_models.md` — including the win/lose conclusion, computed dynamically from whatever the real numbers say, never asserted. |
| `tests/unit/test_statistical.py`, `test_statistical_backtest.py`, `test_generate_statistical_models_report.py` | 21 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended with steps 14–15. New targets: `make statistical-backtest`, `make statistical-report`, `make phase06`. |

**Total test count: 122** (101 from Phases 01–05 + 21 new: 10 in `test_statistical.py`, 7 in `test_statistical_backtest.py`, 4 in `test_generate_statistical_models_report.py`), all passing.

### A refactor of Phase 05's code — done deliberately, verified behavior-preserving

`backtest.py`'s `run_rolling_origin_backtest` was generalized to accept a
`models` dict instead of hardcoding the two Phase 05 baselines. This was
necessary rather than optional: forking the loop for Phase 06 would have
meant two copies of the leakage-critical `history = values[: cutoff_idx +
1]` boundary, which is exactly the kind of duplication that risks the two
copies quietly drifting apart. Before writing any new Phase 06 code, the
full existing test suite (101 tests) was re-run against the refactored
function and **passed unchanged** — Phase 05's own reported numbers are
reproduced identically; nothing about Phase 05's conclusions changed, only
the mechanism became reusable.

---

## The result — reported honestly, including where the hypothesis didn't hold

### Overall (all 5 models, all as-of dates)

| Model | n | WAPE | MAE | Bias |
|---|---|---|---|---|
| Naive | 105 | 1.073 | 2.648 | −0.625 |
| **Seasonal Naive** | 45 | **0.908** | 3.067 | −0.632 |
| SES | 105 | 1.204 | 2.970 | −0.364 |
| Croston | 105 | 1.453 | 3.584 | +0.086 |
| SBA | 105 | 1.421 | 3.504 | +0.032 |

**Seasonal Naive wins overall — Croston and SBA do not outperform the
baselines on this fixture.** On the "intermittent" segment specifically
(the segment Croston's method targets), the result is the same: Croston
WAPE 2.103 and SBA WAPE 2.022, both **worse** than Naive (1.198) and
Seasonal Naive (0.847). This directly contradicts the naive expectation
that "intermittent data + intermittent-demand method = win."

### Why, and a piece of evidence that the explanation holds

The likely cause: Croston's method needs a **reasonable number of nonzero-
demand occurrences** for its separate size/interval smoothing to converge.
Most fixture items have only 3–4 nonzero observations by the earlier
as-of dates. With alpha = 0.1, the smoothed estimates barely move from
their initialization at the *first* nonzero observation — which is a
single, noisy data point, not a converged estimate.

**This isn't just an assertion — the fixture itself provides a supporting
data point.** At the **final holdout** (the most recent as-of date, with
the most history available to each series), the gap closes substantially:

| Model | WAPE at final holdout (2013-01-14) |
|---|---|
| Naive | 1.000 |
| Seasonal Naive | 0.906 |
| SES | 0.922 |
| Croston | 0.912 |
| SBA | **0.909** |

At this point SBA (0.909) is essentially tied with Seasonal Naive (0.906)
and beats Naive and SES — a markedly different picture than the aggregate
table. This is **consistent with** (not proof of) the "needs more data to
converge" explanation. It is not proof: one holdout date, ~10 items, and a
20-day fixture is nowhere near enough to confirm it. It is exactly the
right amount of evidence to say "worth re-testing on the real ~4.6-year
history," which is the honest conclusion this phase draws.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–05: no Kaggle network/credentials in
this sandbox. Every number above is copied from an actual run in this
session. What's specific to this phase: **the central question Phase 06
asks — does the justified method actually help? — cannot be answered by
this fixture.** The fixture proves the methods are implemented correctly
(hand-verified against a worked example, leakage-guarded, tested) and that
the evaluation machinery works. Whether Croston/SBA earn their place in
this project past Phase 06 is a question only the real, much longer
history can answer — and the final-holdout pattern above is a specific,
concrete reason to expect the answer might differ from the fixture's
aggregate result, not a guess.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 122/122 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06             # writes reports/phase06/, then docs/statistical_models.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Statistical forecasting, attempted only where the data justifies it** — not defaulted to because the JD phase list names it | Phase 06's own objective; CLAUDE.md §10: "increase complexity only when justified" |
| **The choice of algorithm documented and reasoned**, since the JD does not prescribe one | Phase 06's own objective: "document the reason for the choice" |
| **Honest evaluation, including a negative result** — reporting that Croston/SBA did not beat the baselines, rather than only reporting favorable numbers | Requirements: "great attention to detail"; CLAUDE.md §19 (honesty/source discipline) |
| **Evidence-based language**, never overclaiming from the final-holdout pattern | CLAUDE.md §13: "associated with," "consistent with," not "proves" |
| **Reusable, maintainable code**: the backtest loop generalized rather than duplicated | CLAUDE.md engineering principles: "modular code... maintainability" |

Not yet covered: ML forecasting (Phase 07), the full evaluation framework
(Phase 08), monitoring, alerts, dashboards, RCA, BigQuery.

---

## Key decisions

- **Croston-family (not generic ETS/ARIMA) is the statistical method
  attempted**, chosen because it directly matches Phase 04's intermittency
  finding — the justification is about matching method to diagnosed data
  pattern, not "try whatever's popular."
- **SES is included as a deliberate comparison point**, not a serious
  candidate — its purpose is to make the "single smoothed level over a
  mostly-zero series" failure mode concrete and measurable, not to win.
- **alpha is fixed** (0.1 for Croston/SBA — the literature's conventional
  default; 0.2 for SES), not optimized per series — `[DECISION]`,
  deliberately avoiding per-series tuning that would risk overfitting on
  short histories and would answer a different question (can alpha be
  tuned to win?) than the one this phase asks (does the method family
  help as-is?).
- **The backtest loop was refactored, not forked**, for Phase 06's model
  set — verified behavior-preserving by re-running Phase 05's full test
  suite unchanged before writing new code.
- **`fct_forecast` is superseded, not appended to** — Phase 06's run
  reloads it with all 5 models via the same `CREATE OR REPLACE TABLE`
  Phase 05 used. Anyone querying it after Phase 06 sees the full set.
- **The report's conclusion is computed from the data, not templated
  text** — `generate_statistical_models_report.py` compares whichever
  models actually have the lowest WAPE and writes the "did/did not
  outperform" sentence accordingly; this was necessary specifically
  because the honest fixture result is the "did not" branch, and the
  generator had to handle that correctly, not just the flattering case.

## Validation

```
$ make test
........................................................................ [ 59%]
..................................................                       [100%]
122 passed in 28.65s

$ make smoke   # 15 steps, ending with the statistical backtest + report
...
[14/15] Running the Phase 06 statistical-models backtest (SES, Croston, SBA)
Backtesting 2 as-of date(s) x 5 model(s): ['croston', 'naive', 'sba', 'seasonal_naive', 'ses']
Wrote .../reports/fixture_smoke_test/phase06/statistical_summary.json:
1260 records, 465 scored, lower-WAPE model overall: seasonal_naive
[15/15] Rendering the statistical models report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every table above is
copied verbatim from that real run, then cleaned up (`make clean-smoke`;
git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** the Croston family did not beat the baselines
  overall or on the intermittent segment specifically — a genuine,
  unfavorable result, reported as such. The final-holdout pattern (SBA
  nearly matching Seasonal Naive once more history exists) is suggestive
  evidence for "needs more data to converge," not proof.
- **`croston_forecast`'s hand-computed test case** (history
  `[0,5,0,0,3,0,0,0,4]`, alpha=0.1 → 2.061...) is worked out explicitly in
  `tests/unit/test_statistical.py` and matches the implementation exactly.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–05.
- **The fixture cannot answer this phase's central question** — stated
  plainly above; this is the phase where that limitation is most
  consequential so far, since the whole point of Phase 06 was to test a
  hypothesis, and 20 days of data cannot test it properly.
- **`docs/statistical_models.md` does not yet exist** — same honesty
  reason as every previous phase's generated document.
- **All earlier phases' limitations still apply unchanged** (no pricing,
  no stockout signal, store-as-hub proxy, Ecuadorian calendar, coarse
  transferred-holiday handling, unvalidated extreme-value fence at scale).

## What to review

1. **`docs/phase_reports/phase06.md`'s honesty** (this document) — confirm
   you're comfortable with a phase whose headline result is "the justified
   method didn't win on the test data available," and that the reasoning
   for still keeping it (final-holdout evidence, sample-size limits) holds
   up under your own read.
2. **The `backtest.py` refactor** — confirm Phase 05's numbers really are
   unchanged (the test suite re-run is the proof; spot-check
   `docs/phase_reports/phase05.md`'s numbers against this phase's rerun if
   you want a second check).
3. **Whether TSB (Teunter-Syntetos-Babai), a further Croston refinement
   that also models demand *probability* rather than just interval, is
   worth adding** before or instead of continuing to ML forecasting
   (Phase 07) — not implemented here to keep this phase's scope to what
   the justification already covers.
4. **Run `make phase01` through `make phase06` locally** once Kaggle
   access exists — this is the phase where the real run matters most so
   far, since the fixture genuinely cannot settle the question it asks.

## Interview questions

- Why was Croston's method chosen over generic ETS or ARIMA, given the JD
  doesn't prescribe an algorithm?
- Walk through why Croston/SBA underperformed the baselines on this
  fixture, and what evidence (not just intuition) supports that
  explanation.
- Why is SES in this comparison at all, given it wasn't expected to win?
- What would change in your conclusion about Croston-family methods if the
  real dataset showed the same pattern as the fixture (baselines still
  win) versus the pattern in the final-holdout table (Croston-family
  catches up with more history)?
- Why was `run_rolling_origin_backtest` refactored instead of duplicated
  for this phase, and how was the refactor verified not to change Phase
  05's results?
- What's the difference between "the method choice is justified" and "the
  method won the backtest," and why does this phase report both honestly
  even when they point in different directions?

---

**STOP — Phase 06 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 07 (Machine Learning Forecasting) has
not started.
