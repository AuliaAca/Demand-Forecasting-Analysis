# Phase 05 — Forecast Baselines: Review Package

**Phase objective (from the Phase 05 prompt):** implement forecasting
baselines and time-aware validation to establish evidence for the JD's
forecasting and forecast-accuracy requirements. Compare Naive and Seasonal
Naive where applicable.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–04 — see below.**

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/forecasting/baselines.py` | `naive_forecast` and `seasonal_naive_forecast` — pure functions, no database or clock access, so a leakage guarantee can be proven directly on them. |
| `src/demandflow/forecasting/metrics.py` | WAPE (primary), MAE, RMSE, forecast bias, and MAPE computed only over nonzero actuals (with the exclusion count reported). |
| `src/demandflow/forecasting/backtest.py` | The rolling-origin backtest harness: `generate_as_of_dates`, `run_rolling_origin_backtest` (the leakage boundary lives here — `history = values[: cutoff_idx + 1]`), `load_fct_forecast` (materializes the Phase 00 plan's `fct_forecast` mart), `summarize_backtest`. |
| `src/demandflow/forecasting/run_backtest.py` | Orchestrates the above against the Phase 03 warehouse; writes `reports/phase05/backtest_summary.json`. |
| `src/demandflow/reporting/generate_forecast_baselines_report.py` | Renders `docs/forecast_baselines.md` — generated, never hand-typed. |
| `configs/project.yaml` (`forecasting:` section) | `horizon_days: 14`, `season_length_days: 7`, `as_of_cadence_days: 7`, `min_history_days: 7` — all `[DECISION]`/`[ASSUMPTION]`, not JD figures. |
| `tests/unit/test_baselines.py`, `test_forecast_metrics.py`, `test_backtest.py`, `test_generate_forecast_baselines_report.py` | 30 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended with steps 12–13 (run backtest, render report). New targets: `make backtest`, `make backtest-report`, `make phase05`. |

**Total test count: 101** (71 from Phases 01–04 + 30 new: 9 in `test_baselines.py`, 8 in `test_forecast_metrics.py`, 9 in `test_backtest.py`, 4 in `test_generate_forecast_baselines_report.py`), all passing.

### The comparison, on the fixture

Using the real config's parameters (14-day horizon, 7-day season, weekly
cadence) against the fixture: 2 as-of dates, 420 forecast rows, 150
scorable.

| Model | n | WAPE | MAE | Bias |
|---|---|---|---|---|
| Naive | 105 | 1.073 | 2.648 | −0.625 |
| Seasonal Naive | 45 | 0.908 | 3.067 | −0.632 |

**Seasonal Naive has the lower WAPE** — a genuine result from an actual run,
not chosen in advance. Both models under-forecast on net (negative bias),
and both have WAPE near or above 1.0 (error comparable to or exceeding
total actual volume), which is expected and unremarkable given Phase 04
already found most development-scope items are intermittent — simple
baselines are known to struggle on intermittent/lumpy series, which is
exactly the literature's motivation for methods like Croston/TSB (candidates
for Phase 06, if justified by evidence).

---

## Time-aware validation — how leakage is actually prevented, not just asserted

CLAUDE.md §10 requires this explicitly, so it's worth being precise about
the mechanism rather than just the intent:

1. **`naive_forecast` and `seasonal_naive_forecast` are pure functions.**
   They take a `history` list and a horizon; nothing else. There is no
   argument through which they could see a value the caller didn't include.
2. **`run_rolling_origin_backtest` builds `history` with `values[: cutoff_idx + 1]`**,
   where `cutoff_idx` is the index of the as-of date itself — a hard,
   syntactic cutoff, not a filter that could be gotten wrong by a `<=` vs
   `<` mistake elsewhere.
3. **This is tested directly, not just described.** `test_baselines.py`
   proves both functions produce a *different* answer when a "future" value
   is appended to history — demonstrating they're sensitive to exactly what
   they're given, which is what makes `backtest.py`'s cutoff the only thing
   that matters. `test_backtest.py` separately proves a concrete case:
   the Naive forecast made as-of 2013-01-07 for (store 1, item 100) equals
   exactly the observed value on 2013-01-07 (5.0 units) — not any later
   value.
4. **No random split anywhere.** As-of dates are a fixed, deterministic
   schedule (`generate_as_of_dates`); nothing is shuffled or randomly held
   out.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–04: no Kaggle network/credentials in
this sandbox. Every number in the comparison table above is copied from an
actual run in this session (not simulated), and the leakage guarantees
were actually tested, not just claimed.

What's specific to this phase: **the "Seasonal Naive wins" result is a
fixture finding, not a claim about Favorita.** On 20 days and ~10 items,
this comparison has very little statistical power — it's included because
it's true of the actual run, not because it's expected to hold at real
scale. Phase 04's own review package made the same point about EDA
findings; it applies here too, more so, since a model "winning" a
comparison is exactly the kind of claim easy to over-read from a small
sample.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 101/101 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05            # writes reports/phase05/, then docs/forecast_baselines.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Forecasting logic and forecast accuracy**, starting from defensible baselines | Requirements: "Understanding of forecasting... and forecast accuracy"; CLAUDE.md §10: "start with defensible baselines and increase complexity only when justified" |
| **Comparing Naive and Seasonal Naive** with real metrics, not an assumed winner | Phase 05's own objective, literally |
| **Time-aware validation**, proven by test rather than asserted | CLAUDE.md §10: "Use time-aware validation. Do not randomly split time-series data without a defensible reason." |
| **Metric choice justified by data characteristics** (WAPE over MAPE, because Phase 04 found intermittent demand) | CLAUDE.md §11: "Metric choice must be justified by data characteristics and business use." |
| Continuing **strong SQL** (bulk fetch, dense-grid reuse) combined with Python where array/sequence logic is clearer than SQL window-function gymnastics | Requirements: "Strong SQL"; engineering judgment on where each tool fits |

Not yet covered: statistical models (Phase 06), ML forecasting (Phase 07),
the full evaluation framework with segment/horizon breakdowns (Phase 08),
monitoring, alerts, dashboards, RCA, BigQuery.

---

## Key decisions

- **Season length = 7 days.** New in this phase, `[DECISION]` — the
  conventional weekly period for daily retail data, and qualitatively
  consistent with Phase 04's day-of-week finding (itself fixture-only and
  provisional, but the right kind of justification: retail demand has
  well-established weekly patterns in the literature independent of this
  specific fixture).
- **Horizon (14 days) and as-of cadence (7 days) carry over unchanged**
  from Phase 00's business scenario (S4/S5) — this phase implements them,
  it doesn't re-decide them.
- **`fct_forecast` is materialized in the warehouse**, matching the table
  the Phase 00 architecture plan named (`as_of_date, horizon, hub, sku,
  target_date, model, forecast`) — Phase 08 can query it directly rather
  than needing Phase 05's Python objects.
- **A target date is scored only if it falls inside that series' own
  active window** (Phase 03's dense grid) — a forecast is still recorded
  for dates beyond it (so `fct_forecast` stays complete), just marked
  `is_scored = False` rather than compared against a value that doesn't
  exist. This mirrors Phase 03's "never fabricate an actual" discipline.
- **The by-horizon-step table is intentionally coarse** — enough to see
  whether error grows with horizon, explicitly not the full
  accuracy-by-segment framework, which the phase prompt and CLAUDE.md's
  phase list assign to Phase 08.
- **A "final holdout" view is derived from the same backtest output**,
  filtered to the single most recent as-of date, rather than run as a
  separately-coded step — satisfies Phase 00 plan assumption A8 without
  duplicating the backtest mechanism.

## Validation

```
$ make test
........................................................................ [ 71%]
.............................                                            [100%]
101 passed in 13.52s

$ make smoke   # 13 steps, ending with the backtest + report generation
...
[12/13] Running the Phase 05 rolling-origin backtest (Naive vs. Seasonal Naive)
Backtesting 2 as-of date(s): [datetime.date(2013, 1, 7), datetime.date(2013, 1, 14)]
Wrote .../reports/fixture_smoke_test/phase05/backtest_summary.json: 420 records,
150 scored, lower-WAPE model: seasonal_naive
[13/13] Rendering the forecast baselines report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; the comparison table
above is copied verbatim from that real run, then cleaned up
(`make clean-smoke`; git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** Seasonal Naive beats Naive on WAPE overall and at the
  final holdout; both models show substantial error and negative bias,
  consistent with Phase 04's intermittency finding for these series.
- **The by-horizon table shows no clean monotonic error growth** with
  horizon on this fixture — expected, given how few points back each cell
  (some horizon steps have single-digit sample sizes). Real data, with far
  more series and as-of dates, should produce a much more stable pattern;
  worth checking once it exists.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–04.
- **The model comparison is not statistically meaningful at this sample
  size** — stated plainly above and worth repeating: a "winner" on 150
  scored points across ~10 items is a demonstration of the mechanism, not
  a finding to act on.
- **`docs/forecast_baselines.md` does not yet exist** — same honesty
  reason as every previous phase's generated document.
- **Every earlier phase's limitations still apply unchanged** (no pricing,
  no stockout signal, store-as-hub proxy, Ecuadorian calendar, coarse
  transferred-holiday handling).

## What to review

1. **`src/demandflow/forecasting/backtest.py`'s leakage boundary**
   (`history = values[: cutoff_idx + 1]`) — this is the single most
   important line in the phase; confirm you're satisfied it's correct
   before Phase 06+ builds more models on the same harness.
2. **The season-length and horizon/cadence parameters** in
   `configs/project.yaml` — adjust now if 7/14/7 isn't what you want
   carried into Phase 06+.
3. **`test_baselines.py`'s leakage-guard tests** — read what they actually
   prove (and don't prove) about the no-leakage guarantee.
4. **Run `make phase01` through `make phase05` locally** once Kaggle
   access exists, and see whether Seasonal Naive still beats Naive at real
   scale, and whether WAPE values look sane for a real intermittent-demand
   dataset.

## Interview questions

- Walk through exactly how a forecast made as-of a given date is
  prevented from seeing data after that date — point to the specific line
  of code, not just the general design.
- Why is WAPE used as the primary metric here instead of MAPE, and what
  does the MAPE exclusion count in the report actually tell you?
- Why does Seasonal Naive have fewer scored records (45) than Naive (105)
  in the fixture backtest, even though both are evaluated on the same
  as-of dates and horizon?
- What's stored in `fct_forecast` for a forecast whose target date falls
  outside a series' active window, and why is it kept rather than dropped?
- Why is the "final holdout" implemented as a filter over the same
  backtest output rather than a separately-run, later-dated backtest?
- If you were told Seasonal Naive beat Naive on the real dataset by a wide
  margin, what would you want to check before trusting that result, given
  what this phase's own fixture-only caveat says about small samples?

---

**STOP — Phase 05 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 06 (Statistical Models) has not started.
