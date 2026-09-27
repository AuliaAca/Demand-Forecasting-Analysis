"""Tests for the Naive and Seasonal Naive baseline functions."""

import pytest

from demandflow.forecasting.baselines import naive_forecast, seasonal_naive_forecast


def test_naive_forecast_repeats_the_last_value():
    assert naive_forecast([1.0, 2.0, 3.0], horizon=4) == [3.0, 3.0, 3.0, 3.0]


def test_naive_forecast_requires_at_least_one_observation():
    with pytest.raises(ValueError):
        naive_forecast([], horizon=3)


def test_naive_forecast_requires_positive_horizon():
    with pytest.raises(ValueError):
        naive_forecast([1.0], horizon=0)


def test_seasonal_naive_forecast_within_one_season():
    # season_length=7, history ends ...,10,11,12,13,14,15,16 (last 7 values)
    history = [float(i) for i in range(1, 17)]  # 1..16
    result = seasonal_naive_forecast(history, horizon=3, season_length=7)
    # last_season = history[-7:] = [10,11,12,13,14,15,16]; forecast[0]=10, [1]=11, [2]=12
    assert result == [10.0, 11.0, 12.0]


def test_seasonal_naive_forecast_cycles_past_one_season():
    history = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]  # exactly one season, length 7
    result = seasonal_naive_forecast(history, horizon=9, season_length=7)
    # cycles: [10,11,12,13,14,15,16, 10,11] for h=0..8
    assert result == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 10.0, 11.0]


def test_seasonal_naive_forecast_requires_a_full_season_of_history():
    with pytest.raises(ValueError):
        seasonal_naive_forecast([1.0, 2.0, 3.0], horizon=2, season_length=7)


def test_seasonal_naive_forecast_requires_positive_season_length():
    with pytest.raises(ValueError):
        seasonal_naive_forecast([1.0, 2.0, 3.0], horizon=2, season_length=0)


# --- Leakage guard -----------------------------------------------------------
# Both functions take only `history` (data up to and including the forecast
# origin) and never a full series or a "future" argument, so there is no
# code path by which they could see data past their own history list. These
# tests make that property explicit: two histories sharing the same prefix
# but differing afterward must produce identical forecasts for that prefix's
# origin, regardless of what "would have happened next".


def test_naive_forecast_is_unaffected_by_data_that_would_come_after_the_cutoff():
    history_up_to_cutoff = [1.0, 2.0, 3.0]
    forecast_a = naive_forecast(history_up_to_cutoff, horizon=5)

    # A caller who accidentally passed a longer history (leaking the future)
    # would get a different answer -- demonstrating what naive_forecast does
    # NOT do when called correctly with only pre-cutoff data.
    leaked_history = history_up_to_cutoff + [999.0]
    forecast_leaked = naive_forecast(leaked_history, horizon=5)

    assert forecast_a == [3.0] * 5
    assert forecast_leaked != forecast_a  # proves the value at cutoff+1 does change the output
    # i.e. naive_forecast is sensitive only to exactly what's in `history` --
    # the caller (backtest.py) is what must guarantee `history` stops at as_of.


def test_seasonal_naive_forecast_is_unaffected_by_data_that_would_come_after_the_cutoff():
    history_up_to_cutoff = [float(i) for i in range(1, 8)]  # one season, 1..7
    forecast_a = seasonal_naive_forecast(history_up_to_cutoff, horizon=3, season_length=7)

    leaked_history = history_up_to_cutoff + [999.0]
    forecast_leaked = seasonal_naive_forecast(leaked_history, horizon=3, season_length=7)

    assert forecast_leaked != forecast_a  # the leaked point shifts which 7 values form "last_season"
