"""Forecast accuracy metrics (CLAUDE.md Section 11).

WAPE is the primary metric: Phase 04's SKU analysis found most
development-scope items are intermittent (many zero-demand days), and MAPE
is undefined at zero actuals while WAPE aggregates naturally and stays
meaningful. MAE and RMSE are reported alongside it; MAPE is computed too,
but only over the subset of points with a nonzero actual, with the
exclusion count reported -- "MAPE when meaningful" (CLAUDE.md Section 11),
not unconditionally.

Every function takes `pairs: list[tuple[actual, forecast]]` -- one shape
used everywhere in this module, so summarize_by_model (backtest.py) doesn't
need to reshape data per metric.
"""

from __future__ import annotations

import math
from typing import Sequence

Pair = tuple[float, float]


def mae(pairs: Sequence[Pair]) -> float | None:
    if not pairs:
        return None
    return sum(abs(a - f) for a, f in pairs) / len(pairs)


def rmse(pairs: Sequence[Pair]) -> float | None:
    if not pairs:
        return None
    return math.sqrt(sum((a - f) ** 2 for a, f in pairs) / len(pairs))


def wape(pairs: Sequence[Pair]) -> float | None:
    """Sum of absolute error / sum of absolute actuals. Robust to zeros in
    a way per-point percentage metrics are not, because the denominator is
    a sum, not a per-point ratio."""
    denom = sum(abs(a) for a, _ in pairs)
    if not denom:
        return None
    return sum(abs(a - f) for a, f in pairs) / denom


def forecast_bias(pairs: Sequence[Pair]) -> float | None:
    """Signed error as a share of total actual volume: positive means the
    model over-forecasts on net, negative means it under-forecasts."""
    denom = sum(abs(a) for a, _ in pairs)
    if not denom:
        return None
    return sum(f - a for a, f in pairs) / denom


def mape_excluding_zero_actuals(pairs: Sequence[Pair]) -> dict:
    nonzero = [(a, f) for a, f in pairs if a != 0]
    excluded = len(pairs) - len(nonzero)
    value = (
        sum(abs((a - f) / a) for a, f in nonzero) / len(nonzero) if nonzero else None
    )
    return {
        "mape": value,
        "included_count": len(nonzero),
        "excluded_zero_actual_count": excluded,
    }


def summarize(pairs: Sequence[Pair]) -> dict:
    mape_result = mape_excluding_zero_actuals(pairs)
    return {
        "n": len(pairs),
        "wape": wape(pairs),
        "mae": mae(pairs),
        "rmse": rmse(pairs),
        "forecast_bias": forecast_bias(pairs),
        **mape_result,
    }
