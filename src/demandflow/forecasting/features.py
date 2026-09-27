"""Leakage-safe feature engineering for Phase 07's ML model.

Two different leakage rules apply to two different kinds of feature here,
and conflating them is the single easiest way to leak the future into an
ML forecaster (unlike the baselines/Croston, which only ever touch
`history`):

1. **History-derived features** (lags, rolling stats, series maturity) --
   computed *only* from `values[: cutoff_idx + 1]`, the exact same slice
   boundary backtest.py's leakage guard uses. These must never look past
   the as-of date.
2. **Target-date context features** (calendar, promotion) -- computed at
   the *target* date, which is in the future relative to the as-of date.
   This is legitimate, not a bug: Phase 00's business scenario assumptions
   S6/S7 state that promotion and holiday calendars are known in advance
   at forecast time (real retail planning schedules both ahead of time).
   What is never used as a feature, at any date, is the target's own
   `unit_sales` -- that is the label, not an input.

Every function here is pure (no database access) so the leakage boundary
is enforced by what's passed in, not by a query filter that could be
gotten wrong elsewhere -- the same design principle as baselines.py.
"""

from __future__ import annotations

import datetime
import statistics
from dataclasses import dataclass
from typing import Any

import duckdb

NUMERIC_FEATURE_NAMES = [
    "horizon_step", "lag_0", "lag_1", "lag_7", "rolling_mean_7", "rolling_mean_14",
    "rolling_std_7", "history_length", "nonzero_share_14",
    "target_day_of_week", "target_is_holiday", "target_is_payday",
    "target_onpromotion", "target_promotion_unknown", "item_perishable", "store_cluster",
]
CATEGORICAL_FEATURE_NAMES = ["item_family", "store_type"]
ALL_FEATURE_NAMES = NUMERIC_FEATURE_NAMES + CATEGORICAL_FEATURE_NAMES


@dataclass(frozen=True)
class DayContext:
    onpromotion_filled: bool
    is_promotion_unknown: bool
    is_holiday: bool
    day_of_week: int
    is_payday: bool


def load_day_context(con: duckdb.DuckDBPyConnection) -> dict[tuple[int, int, datetime.date], DayContext]:
    """One context per (store_nbr, item_nbr, date) actually present in the
    dense fact table -- calendar and promotion info only, never unit_sales,
    so this dict cannot accidentally be used to leak the label.
    """
    rows = con.execute(
        """
        SELECT f.store_nbr, f.item_nbr, f.date,
               f.onpromotion_filled, f.is_promotion_unknown,
               c.is_holiday, c.day_of_week, c.is_payday
        FROM fct_sales_daily f
        JOIN int_calendar_by_store c ON c.store_nbr = f.store_nbr AND c.date = f.date
        """
    ).fetchall()
    return {
        (store_nbr, item_nbr, date): DayContext(
            onpromotion_filled=onpromotion_filled, is_promotion_unknown=is_promotion_unknown,
            is_holiday=is_holiday, day_of_week=day_of_week, is_payday=is_payday,
        )
        for store_nbr, item_nbr, date, onpromotion_filled, is_promotion_unknown, is_holiday, day_of_week, is_payday in rows
    }


def load_static_attributes(
    con: duckdb.DuckDBPyConnection,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Static (non-time-varying) item and store attributes -- no leakage
    risk, since they don't change with the as-of date."""
    item_rows = con.execute("SELECT item_nbr, family, perishable FROM dim_sku").fetchall()
    store_rows = con.execute("SELECT store_nbr, store_type, cluster FROM dim_hub").fetchall()
    items = {item_nbr: {"family": family, "perishable": perishable} for item_nbr, family, perishable in item_rows}
    stores = {store_nbr: {"store_type": store_type, "cluster": cluster} for store_nbr, store_type, cluster in store_rows}
    return items, stores


def _safe_mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _safe_std(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def build_feature_row(
    history: list[float],
    horizon_step: int,
    target_context: DayContext | None,
    item_attrs: dict[str, Any] | None,
    store_attrs: dict[str, Any] | None,
) -> dict[str, Any]:
    """One training/prediction row. `history` must already be the
    leakage-safe slice (values[: cutoff_idx + 1], exactly as in
    backtest.py) -- this function trusts its caller for that boundary,
    the same contract baselines.py's functions have.

    Missing lag/rolling features (insufficient history) are left as
    `float("nan")`, which LightGBM handles natively -- no imputation, no
    silently dropping the row.
    """
    nan = float("nan")
    n = len(history)

    lag_0 = history[-1]
    lag_1 = history[-2] if n >= 2 else nan
    lag_7 = history[-7] if n >= 7 else nan
    last_7 = history[-7:] if n >= 7 else []
    last_14 = history[-14:] if n >= 14 else []
    rolling_mean_7 = _safe_mean(last_7) if last_7 else nan
    rolling_mean_14 = _safe_mean(last_14) if last_14 else nan
    rolling_std_7 = _safe_std(last_7) if len(last_7) >= 2 else nan
    nonzero_share_14 = (
        sum(1 for v in last_14 if v != 0) / len(last_14) if last_14 else nan
    )

    row: dict[str, Any] = {
        "horizon_step": horizon_step,
        "lag_0": lag_0,
        "lag_1": lag_1,
        "lag_7": lag_7,
        "rolling_mean_7": rolling_mean_7,
        "rolling_mean_14": rolling_mean_14,
        "rolling_std_7": rolling_std_7,
        "history_length": n,
        "nonzero_share_14": nonzero_share_14,
        "item_family": item_attrs["family"] if item_attrs else None,
        "item_perishable": item_attrs["perishable"] if item_attrs else nan,
        "store_type": store_attrs["store_type"] if store_attrs else None,
        "store_cluster": store_attrs["cluster"] if store_attrs else nan,
    }

    if target_context is not None:
        row.update(
            target_day_of_week=target_context.day_of_week,
            target_is_holiday=int(target_context.is_holiday),
            target_is_payday=int(target_context.is_payday),
            target_onpromotion=int(target_context.onpromotion_filled),
            target_promotion_unknown=int(target_context.is_promotion_unknown),
        )
    else:
        row.update(
            target_day_of_week=nan, target_is_holiday=nan, target_is_payday=nan,
            target_onpromotion=nan, target_promotion_unknown=nan,
        )
    return row
