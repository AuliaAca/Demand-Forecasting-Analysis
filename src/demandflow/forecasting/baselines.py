"""Naive and Seasonal Naive forecast baselines (CLAUDE.md Section 10:
"start with defensible baselines and increase complexity only when
justified"; Phase 05's objective: "Compare Naive and Seasonal Naive").

Both functions are pure: given a history (ordered oldest -> newest, ending
at the forecast origin) and a horizon, they return exactly `horizon`
forecast values. Neither touches a database or a clock -- that separation
is what makes the leakage-guard tests in tests/unit/test_backtest.py
possible (a forecast provably cannot see data past its own history list).
"""

from __future__ import annotations


def naive_forecast(history: list[float], horizon: int) -> list[float]:
    """Carries the last observed value forward for every horizon step."""
    if not history:
        raise ValueError("naive_forecast requires at least one historical observation")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    return [history[-1]] * horizon


def seasonal_naive_forecast(history: list[float], horizon: int, season_length: int) -> list[float]:
    """Repeats the last full observed season, cycling for horizon > season_length.

    forecast[h] (1-indexed) = the value from exactly `season_length` periods
    before the target date -- the standard seasonal-naive definition. For
    h > season_length this necessarily reuses values from the most recent
    complete season rather than a not-yet-forecast future value.
    """
    if season_length < 1:
        raise ValueError("season_length must be >= 1")
    if len(history) < season_length:
        raise ValueError(
            f"seasonal_naive_forecast requires at least {season_length} historical "
            f"observations (one full season), got {len(history)}"
        )
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    last_season = history[-season_length:]
    return [last_season[h % season_length] for h in range(horizon)]
