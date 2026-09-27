"""Time-aware rolling-origin backtest (CLAUDE.md Section 10: "Use
time-aware validation. Do not randomly split time-series data without a
defensible reason.").

Design: a sequence of as-of dates on a fixed cadence. At each as-of date,
every hub x SKU series' forecast uses *only* history up to and including
that date (grain: hub x SKU x day, ADR 0001 Section 2.1's "store x SKU x
day" development-scope decision). Forecasts are compared against actuals
once they've "arrived" -- a target date is scored only if it falls inside
that series' own active window (Phase 03's int_sales_daily_dense grid), and
left unscored (never fabricated) otherwise.

The most recent as-of date's window is reported separately as a "final
holdout" (Phase 00 plan assumption A8) alongside the full rolling-origin
comparison across every as-of date.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass
from typing import Any

import duckdb

from demandflow.forecasting.baselines import naive_forecast, seasonal_naive_forecast

MODEL_NAIVE = "naive"
MODEL_SEASONAL_NAIVE = "seasonal_naive"


@dataclass(frozen=True)
class ForecastRecord:
    as_of_date: str
    horizon_step: int
    target_date: str
    store_nbr: int
    item_nbr: int
    model: str
    forecast: float
    actual: float | None
    is_scored: bool


def generate_as_of_dates(
    min_date: datetime.date, max_date: datetime.date, cadence_days: int, min_history_days: int
) -> list[datetime.date]:
    """As-of dates on a fixed cadence, starting once `min_history_days` of
    history exist. Does not require the full horizon to fit before
    max_date -- a series near the end of the range simply scores fewer
    horizon steps (see run_rolling_origin_backtest), rather than being
    excluded from the schedule entirely.
    """
    if cadence_days < 1:
        raise ValueError("cadence_days must be >= 1")
    if min_history_days < 1:
        raise ValueError("min_history_days must be >= 1")
    first = min_date + datetime.timedelta(days=min_history_days - 1)
    dates = []
    candidate = first
    while candidate <= max_date:
        dates.append(candidate)
        candidate += datetime.timedelta(days=cadence_days)
    return dates


def load_dense_series(
    con: duckdb.DuckDBPyConnection,
) -> dict[tuple[int, int], tuple[list[datetime.date], list[float]]]:
    """One (dates, values) pair per (store_nbr, item_nbr), both ordered by
    date. Values come straight from fct_sales_daily, so a "history" slice
    of this list already reflects Phase 03's dense zero-fill within the
    series' active window -- there are no gaps to reason about here.
    """
    rows = con.execute(
        "SELECT store_nbr, item_nbr, date, unit_sales FROM fct_sales_daily ORDER BY store_nbr, item_nbr, date"
    ).fetchall()
    series: dict[tuple[int, int], tuple[list[datetime.date], list[float]]] = {}
    dates_by_key: dict[tuple[int, int], list[datetime.date]] = {}
    values_by_key: dict[tuple[int, int], list[float]] = {}
    for store_nbr, item_nbr, d, unit_sales in rows:
        key = (store_nbr, item_nbr)
        dates_by_key.setdefault(key, []).append(d)
        values_by_key.setdefault(key, []).append(unit_sales)
    for key in dates_by_key:
        series[key] = (dates_by_key[key], values_by_key[key])
    return series


def run_rolling_origin_backtest(
    con: duckdb.DuckDBPyConnection,
    as_of_dates: list[datetime.date],
    horizon: int,
    season_length: int,
) -> list[ForecastRecord]:
    series = load_dense_series(con)
    records: list[ForecastRecord] = []

    for (store_nbr, item_nbr), (dates, values) in series.items():
        date_index = {d: i for i, d in enumerate(dates)}
        for as_of in as_of_dates:
            cutoff_idx = date_index.get(as_of)
            if cutoff_idx is None:
                continue  # as_of falls outside this series' active window

            history = values[: cutoff_idx + 1]  # strictly <= as_of: the leakage boundary
            naive_preds = naive_forecast(history, horizon)
            seasonal_preds = (
                seasonal_naive_forecast(history, horizon, season_length)
                if len(history) >= season_length
                else None
            )

            for h in range(1, horizon + 1):
                target_idx = cutoff_idx + h
                target_date = as_of + datetime.timedelta(days=h)
                is_scored = target_idx < len(dates) and dates[target_idx] == target_date
                actual = values[target_idx] if is_scored else None

                records.append(
                    ForecastRecord(
                        as_of_date=as_of.isoformat(), horizon_step=h, target_date=target_date.isoformat(),
                        store_nbr=store_nbr, item_nbr=item_nbr, model=MODEL_NAIVE,
                        forecast=naive_preds[h - 1], actual=actual, is_scored=is_scored,
                    )
                )
                if seasonal_preds is not None:
                    records.append(
                        ForecastRecord(
                            as_of_date=as_of.isoformat(), horizon_step=h, target_date=target_date.isoformat(),
                            store_nbr=store_nbr, item_nbr=item_nbr, model=MODEL_SEASONAL_NAIVE,
                            forecast=seasonal_preds[h - 1], actual=actual, is_scored=is_scored,
                        )
                    )
    return records


def load_fct_forecast(con: duckdb.DuckDBPyConnection, records: list[ForecastRecord]) -> None:
    """Materializes the backtest output as a queryable mart, fct_forecast
    (as_of_date, horizon, hub, sku, target_date, model, forecast) -- the
    table named in the Phase 00 plan's architecture (Section 6.2).
    """
    con.execute(
        """
        CREATE OR REPLACE TABLE fct_forecast (
            as_of_date DATE, horizon_step INTEGER, target_date DATE,
            store_nbr INTEGER, item_nbr BIGINT, model VARCHAR,
            forecast DOUBLE, actual DOUBLE, is_scored BOOLEAN
        )
        """
    )
    for r in records:
        con.execute(
            "INSERT INTO fct_forecast VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [r.as_of_date, r.horizon_step, r.target_date, r.store_nbr, r.item_nbr,
             r.model, r.forecast, r.actual, r.is_scored],
        )


def records_to_dicts(records: list[ForecastRecord]) -> list[dict[str, Any]]:
    return [asdict(r) for r in records]


def _pairs_for(records: list[ForecastRecord], model: str) -> list[tuple[float, float]]:
    return [(r.actual, r.forecast) for r in records if r.is_scored and r.model == model]


def summarize_backtest(records: list[ForecastRecord]) -> dict[str, Any]:
    """Overall comparison across every as-of date, plus a "final holdout"
    view restricted to the single most recent as-of date (Phase 00 plan
    assumption A8) and a coarse by-horizon-step breakdown -- a light
    addition, not the full accuracy-by-segment framework Phase 08 owns.
    """
    from demandflow.forecasting.metrics import summarize as summarize_pairs

    models = sorted({r.model for r in records})
    scored_as_of_dates = sorted({r.as_of_date for r in records if r.is_scored})

    overall = {model: summarize_pairs(_pairs_for(records, model)) for model in models}

    final_holdout: dict[str, Any] = {}
    if scored_as_of_dates:
        final_as_of = scored_as_of_dates[-1]
        final_records = [r for r in records if r.as_of_date == final_as_of]
        final_holdout = {
            "as_of_date": final_as_of,
            "by_model": {model: summarize_pairs(_pairs_for(final_records, model)) for model in models},
        }

    by_horizon: dict[str, dict[int, Any]] = {}
    horizon_steps = sorted({r.horizon_step for r in records})
    for model in models:
        by_horizon[model] = {}
        for h in horizon_steps:
            pairs = [(r.actual, r.forecast) for r in records if r.is_scored and r.model == model and r.horizon_step == h]
            if pairs:
                by_horizon[model][h] = summarize_pairs(pairs)

    winner = None
    comparable = {m: overall[m]["wape"] for m in models if overall[m]["wape"] is not None}
    if comparable:
        winner = min(comparable, key=comparable.get)

    return {
        "as_of_dates_used": [d.isoformat() if isinstance(d, datetime.date) else d for d in sorted({r.as_of_date for r in records})],
        "scored_as_of_dates": scored_as_of_dates,
        "total_records": len(records),
        "total_scored_records": sum(1 for r in records if r.is_scored),
        "overall_by_model": overall,
        "final_holdout": final_holdout,
        "by_horizon_step": by_horizon,
        "lower_wape_model": winner,
    }
