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
from typing import Any, Callable

import duckdb

MODEL_NAIVE = "naive"
MODEL_SEASONAL_NAIVE = "seasonal_naive"

# A model is any (history, horizon) -> forecasts function. It returns None
# (rather than raising) when it cannot produce a forecast from this history
# -- e.g. Seasonal Naive needs a full season, Croston needs at least one
# nonzero observation -- so run_rolling_origin_backtest can skip it for that
# one (series, as_of) combination without the whole backtest failing.
ForecastFn = Callable[[list[float], int], "list[float] | None"]


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


def default_models(season_length: int) -> dict[str, ForecastFn]:
    """The Phase 05 baseline pair, as (history, horizon) -> forecasts | None
    adapters -- ValueError from insufficient history becomes "skip this
    (series, as_of) combination" rather than an exception through the loop.
    """
    from demandflow.forecasting.baselines import naive_forecast, seasonal_naive_forecast

    def _naive(history: list[float], horizon: int) -> list[float] | None:
        return naive_forecast(history, horizon) if history else None

    def _seasonal_naive(history: list[float], horizon: int) -> list[float] | None:
        if len(history) < season_length:
            return None
        return seasonal_naive_forecast(history, horizon, season_length)

    return {MODEL_NAIVE: _naive, MODEL_SEASONAL_NAIVE: _seasonal_naive}


def run_rolling_origin_backtest(
    con: duckdb.DuckDBPyConnection,
    as_of_dates: list[datetime.date],
    horizon: int,
    models: dict[str, ForecastFn] | None = None,
    season_length: int | None = None,
) -> list[ForecastRecord]:
    """Runs every model in `models` over every (series, as_of) combination.

    `models` defaults to Phase 05's Naive + Seasonal Naive pair (built via
    `season_length`, kept as a convenience parameter so Phase 05's own
    call sites don't need to change) -- Phase 06+ passes its own, larger
    `models` dict (e.g. adding SES/Croston/SBA) built with
    demandflow.forecasting.statistical's adapters, reusing this exact same
    leakage-safe loop rather than forking it.
    """
    if models is None:
        if season_length is None:
            raise ValueError("run_rolling_origin_backtest needs either `models` or `season_length`")
        models = default_models(season_length)

    series = load_dense_series(con)
    records: list[ForecastRecord] = []

    for (store_nbr, item_nbr), (dates, values) in series.items():
        date_index = {d: i for i, d in enumerate(dates)}
        for as_of in as_of_dates:
            cutoff_idx = date_index.get(as_of)
            if cutoff_idx is None:
                continue  # as_of falls outside this series' active window

            history = values[: cutoff_idx + 1]  # strictly <= as_of: the leakage boundary
            preds_by_model = {name: fn(history, horizon) for name, fn in models.items()}

            for h in range(1, horizon + 1):
                target_idx = cutoff_idx + h
                target_date = as_of + datetime.timedelta(days=h)
                is_scored = target_idx < len(dates) and dates[target_idx] == target_date
                actual = values[target_idx] if is_scored else None

                for model_name, preds in preds_by_model.items():
                    if preds is None:
                        continue  # this model couldn't forecast from this history
                    records.append(
                        ForecastRecord(
                            as_of_date=as_of.isoformat(), horizon_step=h, target_date=target_date.isoformat(),
                            store_nbr=store_nbr, item_nbr=item_nbr, model=model_name,
                            forecast=preds[h - 1], actual=actual, is_scored=is_scored,
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


def summarize_by_segment(
    records: list[ForecastRecord], item_to_segment: dict[int, str]
) -> dict[str, dict[str, Any]]:
    """WAPE/MAE/etc. per model, broken out by an arbitrary per-item segment
    label (e.g. Phase 04's intermittency classification). Items missing
    from `item_to_segment` are grouped under "unclassified" rather than
    silently dropped.

    A small, generic building block -- not Phase 08's full accuracy-by-
    segment/horizon framework, but a piece Phase 08 can reuse for other
    segment definitions (family, hub, ABC class) once it exists.
    """
    from demandflow.forecasting.metrics import summarize as summarize_pairs

    models = sorted({r.model for r in records})
    segments = sorted(set(item_to_segment.values()) | {"unclassified"})

    result: dict[str, dict[str, Any]] = {}
    for segment in segments:
        if segment == "unclassified":
            segment_records = [r for r in records if r.item_nbr not in item_to_segment]
        else:
            item_nbrs = {item for item, s in item_to_segment.items() if s == segment}
            segment_records = [r for r in records if r.item_nbr in item_nbrs]
        if not segment_records:
            continue
        result[segment] = {
            model: summarize_pairs(_pairs_for(segment_records, model)) for model in models
        }
    return result


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
