"""Tests for the forecast accuracy metrics."""

import math

import pytest

from demandflow.forecasting.metrics import (
    forecast_bias,
    mae,
    mape_excluding_zero_actuals,
    rmse,
    summarize,
    wape,
)


def test_mae_basic():
    pairs = [(10.0, 8.0), (5.0, 5.0), (0.0, 2.0)]
    assert mae(pairs) == pytest.approx((2 + 0 + 2) / 3)


def test_rmse_basic():
    pairs = [(10.0, 8.0), (0.0, 2.0)]
    assert rmse(pairs) == pytest.approx(math.sqrt((4 + 4) / 2))


def test_wape_basic():
    pairs = [(10.0, 8.0), (5.0, 5.0), (0.0, 2.0)]
    # sum|error| = 2+0+2=4; sum|actual| = 10+5+0=15
    assert wape(pairs) == pytest.approx(4 / 15)


def test_wape_is_none_when_all_actuals_are_zero():
    assert wape([(0.0, 1.0), (0.0, 2.0)]) is None


def test_forecast_bias_sign_indicates_over_or_under_forecasting():
    over = forecast_bias([(10.0, 12.0)])  # forecast > actual -> over-forecasts
    under = forecast_bias([(10.0, 8.0)])  # forecast < actual -> under-forecasts
    assert over > 0
    assert under < 0


def test_mape_excludes_zero_actuals_and_reports_the_exclusion_count():
    pairs = [(10.0, 8.0), (0.0, 5.0), (0.0, 3.0), (4.0, 4.0)]
    result = mape_excluding_zero_actuals(pairs)
    assert result["excluded_zero_actual_count"] == 2
    assert result["included_count"] == 2
    # mean(|10-8|/10, |4-4|/4) = mean(0.2, 0.0) = 0.1
    assert result["mape"] == pytest.approx(0.1)


def test_mape_is_none_when_every_actual_is_zero():
    result = mape_excluding_zero_actuals([(0.0, 1.0), (0.0, 2.0)])
    assert result["mape"] is None
    assert result["included_count"] == 0
    assert result["excluded_zero_actual_count"] == 2


def test_summarize_includes_every_metric_and_handles_empty_input():
    empty = summarize([])
    assert empty["n"] == 0
    assert empty["wape"] is None
    assert empty["mae"] is None

    result = summarize([(10.0, 8.0), (5.0, 5.0)])
    assert result["n"] == 2
    assert set(result) == {"n", "wape", "mae", "rmse", "forecast_bias", "mape", "included_count", "excluded_zero_actual_count"}
