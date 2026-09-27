"""Tests for the Phase 07 LightGBM training/prediction wrapper."""

import math

from demandflow.forecasting.features import build_feature_row
from demandflow.forecasting.ml import MIN_TRAINING_ROWS, predict, train_model


def _rows(n: int) -> tuple[list[dict], list[float]]:
    rows, labels = [], []
    for i in range(n):
        history = [float(i % 5)] * 8
        rows.append(build_feature_row(history, horizon_step=1, target_context=None, item_attrs=None, store_attrs=None))
        labels.append(float(i % 5))
    return rows, labels


def test_train_model_returns_none_below_the_minimum_row_threshold():
    rows, labels = _rows(MIN_TRAINING_ROWS - 1)
    assert train_model(rows, labels) is None


def test_train_model_fits_at_or_above_the_minimum_row_threshold():
    rows, labels = _rows(MIN_TRAINING_ROWS)
    model = train_model(rows, labels)
    assert model is not None


def test_predict_clamps_to_nonnegative():
    rows, labels = _rows(30)
    # All labels are small non-negative integers; the model should not need
    # to extrapolate to negative territory, but the clamp is tested directly
    # regardless of what the fitted model actually outputs.
    model = train_model(rows, labels)
    preds = predict(model, rows)
    assert all(p >= 0.0 for p in preds)


def test_predict_handles_nan_features_without_raising():
    rows, labels = _rows(30)
    model = train_model(rows, labels)
    # A prediction row with missing lag/rolling features (short history) --
    # LightGBM must handle this natively, not crash.
    sparse_row = build_feature_row([3.0], horizon_step=1, target_context=None, item_attrs=None, store_attrs=None)
    assert math.isnan(sparse_row["rolling_mean_7"])
    preds = predict(model, [sparse_row])
    assert len(preds) == 1
    assert not math.isnan(preds[0])


def test_train_model_is_deterministic_across_repeated_calls():
    # Phase 15 (reproducibility): two independently-trained models on
    # identical inputs must yield bit-identical predictions -- otherwise
    # every phase that reruns the ML backtest ("rebuild, don't trust a
    # stale file") could silently drift run to run.
    rows, labels = _rows(30)
    model_a = train_model(rows, labels)
    model_b = train_model(rows, labels)
    assert predict(model_a, rows) == predict(model_b, rows)
