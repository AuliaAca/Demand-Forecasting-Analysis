# Phase 07 — Machine Learning Forecasting: Review Package

**Phase objective (from the Phase 07 prompt):** determine whether machine-
learning forecasting adds measurable value. If justified, implement
leakage-safe features and an ML model, then compare against simpler
approaches. Treat ML forecasting as a JD bonus, not a mandatory
requirement.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–06. A real leakage bug was found and fixed
while building this phase — documented in full below, not glossed over.**

---

## Whether ML is justified here (required before implementation, per the objective)

Phase 06 ended with baselines still winning and Croston/SBA underperforming
on this fixture. That alone would argue against trying ML too. The
specific reason to try it anyway: **a *global* model** — one model fit
across every hub × SKU series pooled together, not one per series — can
learn shared cross-sectional patterns even from a short per-series
history. This is the established, specific advantage ML brings to panel
retail-forecasting data (e.g. the M5 competition's top solutions were
global gradient-boosting models), and it is a different mechanism than
what Croston/SES/Seasonal Naive can use — those only ever see one series
at a time. Given this project's development scope has real cross-sectional
breadth (multiple stores, multiple items, multiple families) even where
per-series history is short, this is a genuine, mechanism-specific reason
to expect ML might help where per-series statistical methods could not —
not "try it because it's on the phase list."

**LightGBM** was used, per Phase 00's own plan (ADR 0001), and consistent
with the M5-competition precedent above. Generic deep learning was not
considered — nothing about this dataset's scale or structure calls for it,
and CLAUDE.md §9 ("do not add infrastructure only for appearance") argues
against it.

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/forecasting/features.py` | Leakage-safe feature engineering — the module docstring states the two different leakage rules that apply (history-derived vs. target-date-context features) explicitly, since conflating them is the easiest way to leak here. |
| `src/demandflow/forecasting/ml.py` | LightGBM training/prediction wrapper — small, fixed (untuned) hyperparameters; returns `None` rather than fitting on too little data. |
| `src/demandflow/forecasting/run_ml_backtest.py` | Builds every (series, as-of, horizon) example, splits strictly by time into train/holdout, trains one global model, and evaluates it against Naive/Seasonal Naive/SBA on the exact same holdout rows. |
| `src/demandflow/reporting/generate_ml_report.py` | Renders `docs/ml_forecasting.md` — states plainly if the model didn't train at all (small-data runs), and computes the win/lose conclusion from the real numbers. |
| `pyproject.toml` | New dependency: `lightgbm>=4.0`. |
| `tests/unit/test_features.py`, `test_ml.py`, `test_ml_backtest.py`, `test_generate_ml_report.py` | 22 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended with steps 16–17. New targets: `make ml-backtest`, `make ml-report`, `make phase07`. |

**Total test count: 144** (122 from Phases 01–06 + 22 new: 7 in `test_features.py`, 4 in `test_ml.py`, 7 in `test_ml_backtest.py`, 4 in `test_generate_ml_report.py`), all passing.

### The feature set, and why each kind of feature is leakage-safe

| Feature | Source | Why it's safe |
|---|---|---|
| `lag_0`, `lag_1`, `lag_7` | History up to and including the as-of date | Same `values[: cutoff_idx + 1]` boundary `backtest.py` uses |
| `rolling_mean_7/14`, `rolling_std_7`, `nonzero_share_14` | Same history slice | Same boundary; left as `NaN` (not imputed) when history is too short — LightGBM handles missing values natively |
| `history_length` | Same history slice | A "series maturity" signal, same boundary |
| `target_day_of_week`, `target_is_holiday`, `target_is_payday` | The **target** date's calendar | Legitimate under Phase 00 assumption S7: holiday/calendar information is known in advance in this project's scenario |
| `target_onpromotion`, `target_promotion_unknown` | The **target** date's resolved promotion status | Legitimate under assumption S6: promotions are known in advance |
| `item_family`, `item_perishable`, `store_type`, `store_cluster` | Static dimension attributes | Don't vary with time — no leakage risk |
| `horizon_step` | The step being forecast | Not data-derived at all |

What is **never** a feature, at any date: the target's own `unit_sales` —
that value is the training label, and nothing else.

---

## A real leakage bug, found and fixed while building this phase

The feature-level leakage rules above were correct from the start and are
tested directly. The bug was **structural**, in how training/holdout
examples were split — worth documenting in detail since it's exactly the
kind of thing "leakage-safe" can miss if you only check features and not
the split itself.

**The bug:** the first implementation split training/holdout purely by
`as_of_date` (`training = examples where as_of_date != holdout_as_of`).
That's insufficient: an example from an **earlier** as-of date with a
**long horizon** can have a `target_date` that lands on or after the
holdout's own as-of date. Concretely, on this fixture: as-of `2013-01-07`
with a 14-day horizon reaches `target_date = 2013-01-21` — which overlaps
the exact dates (`2013-01-15` through `2013-01-20`) the holdout (as-of
`2013-01-14`) is later asked to predict. The model was trained on rows
whose **label** was the true `unit_sales` for those dates, then scored on
predicting those same (store, item, date) triples from a closer-range
as-of date. It had memorized the answer.

**How it was caught:** the first run's result looked *too* good — LightGBM
at WAPE 0.641 versus Seasonal Naive's 0.906, a implausibly large gap for
69 training rows. That suspicion, not a test, is what triggered the
investigation — worth being honest that this was caught by scrutinizing an
unexpectedly strong result, not by a test written in advance.

**The fix:** the training filter now also requires `target_date <=
holdout_as_of_date`. A label dated exactly on the holdout's as-of date is
safe (the holdout's own history already legitimately knows that value via
`lag_0`); nothing dated after it may be a training label. This is now
locked in by `test_no_training_example_targets_a_date_the_holdout_will_evaluate`,
which asserts the invariant directly and confirms the filter isn't
vacuous (some examples really are excluded by it).

**The corrected result:** LightGBM's WAPE moved from 0.641 (leaked) to
0.825 (fixed) — still the best of the four models compared, but a much
smaller, more credible margin. The leaked number is not reported anywhere
in this project's committed output; only the corrected one is.

---

## The result — corrected, and reported with appropriate caution

### Holdout comparison (as-of `2013-01-14`, 18 scorable rows)

| Model | WAPE | MAE | Bias |
|---|---|---|---|
| Naive | 1.000 | 5.889 | −1.000 |
| Seasonal Naive | 0.906 | 5.333 | −0.811 |
| SBA | 0.909 | 5.355 | −0.674 |
| **LightGBM** | **0.825** | 4.857 | −0.780 |

**LightGBM has the lowest WAPE** — a genuine, leakage-checked result, not
cherry-picked or leaked. The improvement over Seasonal Naive is real but
modest (0.906 → 0.825), on only 18 scorable holdout rows. Top feature
importances (`target_day_of_week`, `history_length`,
`target_promotion_unknown`, `lag_7`) are sensible — calendar and history-
maturity signals, not something that looks like an accidental leakage
channel.

**How much weight this can honestly bear:** very little, on its own. 18
rows is not enough to call this result statistically meaningful — the
right read is "encouraging, worth re-testing at real scale," the same
caveat every fixture-derived comparison in this project carries, not
"LightGBM is proven better."

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–06: no Kaggle network/credentials in
this sandbox. What's specific to this phase: with only 69 training rows
and 18 holdout rows, this is the **smallest** evaluation of any phase so
far — smaller than Phase 06's already-small 150 scored records. The
justification for trying ML (cross-sectional pooling across many series)
is real, but testing whether it actually pays off needs far more series
and far more history than a 20-day, 10-item fixture can offer.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 144/144 pass on this machine too
make phase01
make phase02
make phase03
make phase04
make phase05
make phase06
make phase07             # writes reports/phase07/, then docs/ml_forecasting.md
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Machine-learning forecasting, explicitly a bonus, not a requirement** | CLAUDE.md §5: "exposure to... machine-learning forecasting" is a bonus signal |
| **Leakage-safe feature engineering**, the phase's own explicit ask | Phase 07's objective: "implement leakage-safe features"; CLAUDE.md §10 |
| **Rigor over a flattering result**: an implausibly good number was investigated rather than reported | Requirements: "great attention to detail" |
| **Comparison against simpler approaches**, on identical holdout rows | Phase 07's objective: "compare against simpler approaches" |
| **Documented reasoning for the method choice** | Consistent with Phase 06's same requirement, applied here to LightGBM |

Not yet covered: the full evaluation framework (Phase 08), monitoring,
alerts, dashboards, RCA, BigQuery.

---

## Key decisions

- **Train/holdout split by `target_date`, not `as_of_date`** — the fix
  above. This is the single most important design decision in this phase.
- **One held-out split, not walk-forward retraining at every as-of date**
  — Phases 05–06's training-free methods are backtested at every as-of
  date cheaply; retraining a model at each one would multiply training
  cost for a bonus phase. A deliberate scope trade-off, not an oversight.
- **Hyperparameters are small and fixed** (`num_leaves=7,
  min_data_in_leaf=3`, 50 trees), not tuned — same reasoning as Phase 06's
  fixed alpha: tuning on this little data answers "can this look good on
  69 rows," not this phase's actual question.
- **`MIN_TRAINING_ROWS` is single-sourced in `train_model`** — a second
  bug was caught and fixed while writing tests: the orchestrator
  originally re-derived `insufficient_training_data` from its own
  separately-imported copy of the same threshold, which could silently
  drift from what `train_model` actually decided. Fixed to derive it from
  `model is None` directly — one source of truth, not two copies of the
  same check.
- **Predictions are clamped at zero** — LightGBM regression is
  unconstrained; negative unit-sales forecasts aren't meaningful,
  `[DECISION]` not a JD figure.

## Validation

```
$ make test
........................................................................ [ 50%]
........................................................................ [100%]
144 passed in 32.23s

$ make smoke   # 17 steps, ending with the ML backtest + report
...
[16/17] Running the Phase 07 ML backtest (LightGBM, leakage-safe features)
280 total examples; 69 training rows (as-of dates before 2013-01-14);
112 holdout rows (18 scorable)
Wrote .../reports/fixture_smoke_test/phase07/ml_summary.json:
model_trained=True, lower-WAPE model on holdout=lightgbm
[17/17] Rendering the ML forecasting report (fixture preview — NOT the real report)
Smoke test complete.
```

Both commands were actually run in this session; every number above is
copied verbatim from that real, leakage-fixed run, then cleaned up
(`make clean-smoke`; git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture:** LightGBM has the lowest WAPE among all four models
  compared, by a real but modest margin, after fixing a genuine leakage
  bug that had inflated the result. Feature importances are dominated by
  calendar (`target_day_of_week`), history maturity, and promotion
  signals — a sensible pattern, not a red flag for a different leak.
- **The leakage bug itself is a finding worth keeping**: it's concrete
  evidence of why this phase's "leakage-safe features" framing needed to
  extend to the train/test split mechanism, not just the feature
  computation.

## Limitations

- **Real Kaggle files still unverified** — unchanged from Phases 01–06.
- **18 scorable holdout rows cannot support a confident conclusion** —
  stated plainly above; this is the smallest evaluation of any phase so
  far, on the phase making the boldest claim (a model beating every
  baseline).
- **Hyperparameters are untuned** — a reasonable next step once real data
  makes tuning meaningful rather than risky.
- **`docs/ml_forecasting.md` does not yet exist** — same honesty reason as
  every previous phase's generated document.
- **All earlier phases' limitations still apply unchanged** (no pricing,
  no stockout signal, store-as-hub proxy, Ecuadorian calendar, coarse
  transferred-holiday handling, unvalidated extreme-value fence at scale).

## What to review

1. **The leakage bug and its fix**, above — read the exact filter in
   `run_ml_backtest.py` (`target_date <= holdout_as_of_date`) against the
   explanation and confirm you're satisfied it's correct.
2. **Whether one held-out split is an acceptable evaluation design for
   this bonus phase**, versus walk-forward retraining — the trade-off is
   explained above; tell me if you'd rather see the more expensive version.
3. **The feature list** in `features.py` — anything you'd add or remove
   before the real run, where feature importance will actually be
   meaningful across thousands of rows instead of 69?
4. **Run `make phase01` through `make phase07` locally** once Kaggle
   access exists — given how small this phase's fixture evaluation is,
   this is the phase where the real run's result matters most so far.

## Interview questions

- Walk through the leakage bug in detail: why did splitting by `as_of_date`
  alone fail, and why does adding `target_date <= holdout_as_of_date` fix
  it completely?
- What made you suspicious of the first (leaked) result enough to
  investigate, rather than just reporting it?
- Why is a *global* model — one model across every series — specifically
  the argument for trying ML here, rather than "ML is generally powerful"?
- Why are target-date calendar and promotion features safe to use even
  though they're chronologically in the future relative to the as-of date?
- Why does this phase use one held-out split instead of the walk-forward
  backtest Phases 05–06 used for their training-free methods?
- If the real dataset showed LightGBM's advantage growing, shrinking, or
  reversing compared to this fixture's result, what would each of those
  outcomes actually tell you?

---

**STOP — Phase 07 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 08 (Forecast Evaluation) has not started.
