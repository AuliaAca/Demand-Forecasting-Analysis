"""Tests for the Phase 06 statistical forecasting methods."""

import pytest

from demandflow.forecasting.statistical import croston_forecast, ses_forecast


def test_ses_forecast_is_flat_and_uses_the_smoothed_level():
    result = ses_forecast([10.0, 10.0, 10.0], horizon=3, alpha=0.2)
    assert result == [10.0, 10.0, 10.0]  # constant history -> level stays 10 regardless of alpha
    assert len(set(result)) == 1  # flat forecast


def test_ses_forecast_requires_history_and_valid_alpha():
    with pytest.raises(ValueError):
        ses_forecast([], horizon=2)
    with pytest.raises(ValueError):
        ses_forecast([1.0], horizon=2, alpha=0)
    with pytest.raises(ValueError):
        ses_forecast([1.0], horizon=0)


def test_croston_forecast_matches_hand_computed_value():
    # Hand-traced in the phase review package: z_hat=4.72, p_hat=2.29 at alpha=0.1
    history = [0, 5, 0, 0, 3, 0, 0, 0, 4]
    result = croston_forecast(history, horizon=3, alpha=0.1)
    assert result == pytest.approx([4.72 / 2.29] * 3)


def test_sba_applies_the_bias_correction_to_croston():
    history = [0, 5, 0, 0, 3, 0, 0, 0, 4]
    croston = croston_forecast(history, horizon=1, alpha=0.1, variant="croston")
    sba = croston_forecast(history, horizon=1, alpha=0.1, variant="sba")
    assert sba[0] == pytest.approx(croston[0] * (1 - 0.1 / 2))
    assert sba[0] < croston[0]  # SBA is a downward bias correction


def test_croston_forecast_on_all_zero_history_returns_zero():
    assert croston_forecast([0.0, 0.0, 0.0], horizon=2) == [0.0, 0.0]


def test_croston_forecast_on_single_nonzero_observation():
    assert croston_forecast([7.0], horizon=2) == [7.0, 7.0]


def test_croston_forecast_flat_across_horizon():
    result = croston_forecast([0, 3, 0, 5], horizon=4)
    assert len(set(result)) == 1


def test_croston_forecast_rejects_bad_params():
    with pytest.raises(ValueError):
        croston_forecast([], horizon=2)
    with pytest.raises(ValueError):
        croston_forecast([1.0], horizon=0)
    with pytest.raises(ValueError):
        croston_forecast([1.0], horizon=2, alpha=1.5)
    with pytest.raises(ValueError):
        croston_forecast([1.0], horizon=2, variant="ets")


# --- Leakage guard, matching the pattern in test_baselines.py ----------------


def test_croston_forecast_is_sensitive_only_to_its_own_history_argument():
    history_up_to_cutoff = [0, 5, 0, 0, 3]
    forecast_a = croston_forecast(history_up_to_cutoff, horizon=2, alpha=0.1)
    leaked_history = history_up_to_cutoff + [999.0]
    forecast_leaked = croston_forecast(leaked_history, horizon=2, alpha=0.1)
    assert forecast_leaked != forecast_a


def test_ses_forecast_is_sensitive_only_to_its_own_history_argument():
    history_up_to_cutoff = [1.0, 2.0, 3.0]
    forecast_a = ses_forecast(history_up_to_cutoff, horizon=2, alpha=0.2)
    leaked_history = history_up_to_cutoff + [999.0]
    forecast_leaked = ses_forecast(leaked_history, horizon=2, alpha=0.2)
    assert forecast_leaked != forecast_a
