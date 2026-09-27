"""Phase 07 entrypoint.

Design: build every (series, as-of date, horizon step) example using the
same as-of-date schedule as Phases 05-06 (for direct comparability), then
split strictly by time -- everything before the final as-of date trains
the model; the final as-of date is the held-out test set. This matches
Phase 00 plan assumption A8 ("rolling-origin backtests plus a final
holdout"): Phases 05-06's training-free methods were backtested at *every*
as-of date cheaply; the ML model requires actual training, so it is
evaluated via one held-out split rather than walk-forward retraining at
each as-of date -- a deliberate scope/cost trade-off for a bonus phase
(CLAUDE.md Section 5), documented in docs/phase_reports/phase07.md, not an
oversight.

For a direct, self-contained comparison, Naive / Seasonal Naive / SBA
(Phase 06's least-bad statistical model) are also evaluated on the exact
same held-out examples, using the exact same history each ML example was
built from.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.forecasting.backtest import generate_as_of_dates, load_dense_series
from demandflow.forecasting.baselines import naive_forecast, seasonal_naive_forecast
from demandflow.forecasting.features import build_feature_row, load_day_context, load_static_attributes
from demandflow.forecasting.metrics import summarize as summarize_pairs
from demandflow.forecasting.ml import MIN_TRAINING_ROWS, predict, train_model
from demandflow.forecasting.statistical import croston_forecast

logger = logging.getLogger(__name__)

MODEL_LIGHTGBM = "lightgbm"
MODEL_NAIVE = "naive"
MODEL_SEASONAL_NAIVE = "seasonal_naive"
MODEL_SBA = "sba"


def build_examples(
    series: dict, as_of_dates: list[datetime.date], horizon: int, day_context: dict, item_attrs: dict, store_attrs: dict
) -> list[dict]:
    """One example per (series, as_of, horizon_step): features (leakage-safe,
    see features.py), the actual label if scorable, and `history` (kept
    alongside so the same example can also be scored by the non-ML models
    for a same-rows comparison)."""
    examples = []
    for (store_nbr, item_nbr), (dates, values) in series.items():
        date_index = {d: i for i, d in enumerate(dates)}
        item_attr = item_attrs.get(item_nbr)
        store_attr = store_attrs.get(store_nbr)
        for as_of in as_of_dates:
            cutoff_idx = date_index.get(as_of)
            if cutoff_idx is None:
                continue
            history = values[: cutoff_idx + 1]  # the leakage boundary -- same as backtest.py
            for h in range(1, horizon + 1):
                target_idx = cutoff_idx + h
                target_date = as_of + datetime.timedelta(days=h)
                is_scored = target_idx < len(dates) and dates[target_idx] == target_date
                actual = values[target_idx] if is_scored else None
                target_ctx = day_context.get((store_nbr, item_nbr, target_date))
                features = build_feature_row(history, h, target_ctx, item_attr, store_attr)
                examples.append(
                    {
                        "as_of_date": as_of.isoformat(), "store_nbr": store_nbr, "item_nbr": item_nbr,
                        "horizon_step": h, "target_date": target_date.isoformat(),
                        "features": features, "history": history, "actual": actual, "is_scored": is_scored,
                    }
                )
    return examples


def _comparison_forecast(model: str, history: list[float], horizon_step: int, season_length: int) -> float | None:
    """The other models' forecast for one horizon step, from the same
    history an ML example used -- all flat-across-horizon, so index 0
    covers every step; wrapped to return None rather than raise when a
    model can't forecast from this history (mirrors backtest.py's contract)."""
    try:
        if model == MODEL_NAIVE:
            return naive_forecast(history, horizon_step)[-1]
        if model == MODEL_SEASONAL_NAIVE:
            if len(history) < season_length:
                return None
            return seasonal_naive_forecast(history, horizon_step, season_length)[-1]
        if model == MODEL_SBA:
            return croston_forecast(history, horizon_step, variant="sba")[-1]
    except ValueError:
        return None
    raise ValueError(f"unknown comparison model {model!r}")


def run_and_write(
    cfg: ProjectConfig | None = None,
    db_path: Path | None = None,
    out_dir: Path | None = None,
) -> dict:
    cfg = cfg or load_config()
    db_path = db_path or (cfg.paths.data_dir / "warehouse" / "demandflow.duckdb")
    if not db_path.exists():
        raise FileNotFoundError(
            f"Expected {db_path} to exist. Run demandflow.transform.build_warehouse first."
        )
    out_dir = out_dir or (cfg.paths.reports_dir / "phase07")
    out_dir.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(db_path)) as con:
        (min_date, max_date) = con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone()
        if min_date is None:
            raise ValueError("fct_sales_daily is empty -- nothing to backtest.")

        as_of_dates = generate_as_of_dates(
            min_date, max_date,
            cadence_days=cfg.forecasting.as_of_cadence_days,
            min_history_days=cfg.forecasting.min_history_days,
        )
        series = load_dense_series(con)
        day_context = load_day_context(con)
        item_attrs, store_attrs = load_static_attributes(con)

    examples = build_examples(series, as_of_dates, cfg.forecasting.horizon_days, day_context, item_attrs, store_attrs)

    holdout_as_of = max(as_of_dates).isoformat() if as_of_dates else None
    # Splitting on as_of_date alone is NOT sufficient: an earlier as-of date
    # with a long horizon can have a target_date that lands on or after the
    # holdout's own as-of date -- e.g. as_of=01-07 with horizon=14 reaches
    # target_date=01-21, which overlaps the very dates the holdout (as_of=
    # 01-14) is asked to predict. Training on that label would let the
    # model memorize the answer for a (store, item, date) it is later
    # scored on -- a real leak, not merely a feature-side one. So training
    # examples must also have target_date <= holdout_as_of: a label at
    # exactly holdout_as_of is safe (the holdout's own history already
    # legitimately knows that value via lag_0), but nothing dated after it.
    training_examples = [
        e for e in examples
        if e["is_scored"] and e["as_of_date"] != holdout_as_of and e["target_date"] <= holdout_as_of
    ]
    holdout_examples = [e for e in examples if e["as_of_date"] == holdout_as_of]
    scored_holdout = [e for e in holdout_examples if e["is_scored"]]

    logger.info(
        "%d total examples; %d training rows (as-of dates before %s); %d holdout rows (%d scorable)",
        len(examples), len(training_examples), holdout_as_of, len(holdout_examples), len(scored_holdout),
    )

    model = train_model(
        [e["features"] for e in training_examples], [e["actual"] for e in training_examples]
    )
    # train_model() is the single authority on whether there's enough data
    # (it owns the MIN_TRAINING_ROWS check internally) -- re-deriving the
    # same condition here from a separately-imported copy of that constant
    # would risk silently drifting out of sync with what train_model
    # actually decided. `model is None` is exactly and only true when
    # training was skipped for this reason.
    insufficient_training_data = model is None

    pairs_by_model: dict[str, list[tuple[float, float]]] = {
        MODEL_NAIVE: [], MODEL_SEASONAL_NAIVE: [], MODEL_SBA: [],
    }
    if model is not None:
        pairs_by_model[MODEL_LIGHTGBM] = []
        ml_preds = predict(model, [e["features"] for e in scored_holdout])
        for e, pred in zip(scored_holdout, ml_preds):
            pairs_by_model[MODEL_LIGHTGBM].append((e["actual"], pred))

    for e in scored_holdout:
        for m in (MODEL_NAIVE, MODEL_SEASONAL_NAIVE, MODEL_SBA):
            forecast = _comparison_forecast(m, e["history"], e["horizon_step"], cfg.forecasting.season_length_days)
            if forecast is not None:
                pairs_by_model[m].append((e["actual"], forecast))

    holdout_by_model = {m: summarize_pairs(pairs) for m, pairs in pairs_by_model.items()}
    wapes = {m: v["wape"] for m, v in holdout_by_model.items() if v["wape"] is not None}
    winner = min(wapes, key=wapes.get) if wapes else None

    feature_importance = None
    if model is not None:
        feature_importance = dict(
            sorted(
                zip(model.feature_name_, [int(v) for v in model.feature_importances_]),
                key=lambda kv: kv[1], reverse=True,
            )
        )

    summary = {
        "as_of_dates_used": [d.isoformat() for d in as_of_dates],
        "holdout_as_of_date": holdout_as_of,
        "total_examples": len(examples),
        "training_rows": len(training_examples),
        "holdout_rows": len(holdout_examples),
        "holdout_scored_rows": len(scored_holdout),
        "model_trained": model is not None,
        "insufficient_training_data": insufficient_training_data,
        "min_training_rows_required": MIN_TRAINING_ROWS,
        "holdout_by_model": holdout_by_model,
        "lower_wape_model": winner,
        "feature_importance": feature_importance,
    }

    summary_path = out_dir / "ml_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s: model_trained=%s, lower-WAPE model on holdout=%s",
        summary_path, summary["model_trained"], winner,
    )
    return {"summary_path": summary_path, "summary": summary, "model": model}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Model trained: {result['summary']['model_trained']}")
    print(f"Lower-WAPE model on holdout: {result['summary']['lower_wape_model']}")


if __name__ == "__main__":
    _main()
