"""Tests for Phase 07's leakage-safe feature engineering."""

import math

from demandflow.forecasting.features import DayContext, build_feature_row


def test_build_feature_row_uses_only_the_given_history():
    history = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]  # exactly 7 -> lag_7 and rolling_7 available
    row = build_feature_row(history, horizon_step=3, target_context=None, item_attrs=None, store_attrs=None)
    assert row["lag_0"] == 7.0
    assert row["lag_1"] == 6.0
    assert row["lag_7"] == 1.0
    assert row["rolling_mean_7"] == sum(history) / 7
    assert row["history_length"] == 7
    assert row["horizon_step"] == 3


def test_build_feature_row_leaves_unavailable_lags_as_nan_not_zero():
    history = [5.0, 6.0]  # too short for lag_7 / rolling_7 / rolling_14
    row = build_feature_row(history, horizon_step=1, target_context=None, item_attrs=None, store_attrs=None)
    assert math.isnan(row["lag_7"])
    assert math.isnan(row["rolling_mean_7"])
    assert math.isnan(row["rolling_mean_14"])
    assert row["lag_0"] == 6.0  # what IS available is still populated
    assert row["lag_1"] == 5.0


def test_build_feature_row_is_unaffected_by_data_after_the_cutoff():
    # Same leakage-guard pattern as test_baselines.py / test_statistical.py.
    history_up_to_cutoff = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    row_a = build_feature_row(history_up_to_cutoff, 1, None, None, None)
    leaked = history_up_to_cutoff + [999.0]
    row_leaked = build_feature_row(leaked, 1, None, None, None)
    assert row_a["lag_0"] != row_leaked["lag_0"]
    assert row_a["rolling_mean_7"] != row_leaked["rolling_mean_7"]


def test_build_feature_row_nonzero_share_reflects_intermittency():
    mostly_zero = [0.0] * 12 + [5.0, 3.0]  # 14 points, 2 nonzero
    row = build_feature_row(mostly_zero, 1, None, None, None)
    assert row["nonzero_share_14"] == 2 / 14


def test_build_feature_row_includes_target_context_when_given():
    ctx = DayContext(
        onpromotion_filled=True, is_promotion_unknown=False, is_holiday=True, day_of_week=6, is_payday=False
    )
    row = build_feature_row([1.0, 2.0], 1, ctx, None, None)
    assert row["target_onpromotion"] == 1
    assert row["target_is_holiday"] == 1
    assert row["target_day_of_week"] == 6
    assert row["target_promotion_unknown"] == 0
    assert row["target_is_payday"] == 0


def test_build_feature_row_target_context_missing_leaves_nan_not_a_guess():
    row = build_feature_row([1.0, 2.0], 1, None, None, None)
    assert math.isnan(row["target_is_holiday"])
    assert math.isnan(row["target_onpromotion"])


def test_build_feature_row_includes_static_attributes():
    item_attrs = {"family": "DAIRY", "perishable": 1}
    store_attrs = {"store_type": "A", "cluster": 3}
    row = build_feature_row([1.0], 1, None, item_attrs, store_attrs)
    assert row["item_family"] == "DAIRY"
    assert row["item_perishable"] == 1
    assert row["store_type"] == "A"
    assert row["store_cluster"] == 3
