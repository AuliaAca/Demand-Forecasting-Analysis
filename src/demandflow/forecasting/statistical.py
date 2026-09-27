"""Statistical forecasting methods (Phase 06).

Phase 06's objective is conditional: "Implement and evaluate statistical
forecasting only if justified by the data and baseline results." The
justification here, in order:

1. Phase 04's SKU analysis (demandflow.analysis.eda.sku_velocity_and_intermittency)
   classified most development-scope items as intermittent or lumpy (many
   zero-demand days, high demand-size variability) using the conventional
   Syntetos-Boylan-Croston thresholds.
2. Phase 05's baseline backtest showed both Naive and Seasonal Naive with
   WAPE at or above 1.0 on these series -- consistent with the literature:
   generic smoothing methods that don't distinguish "no demand" from "small
   demand" perform poorly on intermittent series, because a run of zeros
   pulls a single smoothed level toward zero regardless of the size of
   demand when it does occur.
3. Croston's method (Croston, 1972) and its bias-corrected variant SBA
   (Syntetos & Boylan, 2005) exist specifically to address this: they
   smooth demand *size* and *inter-demand interval* separately, rather than
   smoothing the raw (mostly-zero) series directly.

So the method implemented here is Croston-family, not generic ETS/ARIMA --
those assume a continuous, non-intermittent series, which Phase 04 already
found does not describe most of this development scope. Simple Exponential
Smoothing (SES) is included too, specifically as the "what intermittency-
naive statistical smoothing does" comparison point: applying one smoothed
level to a mostly-zero series is the exact failure mode Croston's method
was invented to fix, so SES is here to make that comparison concrete, not
because it's expected to win.

All three are implemented from scratch (no statsmodels/pmdarima dependency)
-- they are each one or two smoothing recurrences, and a hand-rolled
implementation is the ordinary way Croston/SBA are done in practice (no
mainstream Python statistics library implements them natively). This keeps
the dependency footprint unchanged (CLAUDE.md Section 9: prefer free/local,
do not add infrastructure only for appearance).

[DECISION] alpha is a fixed default (0.1 for the Croston family, matching
Croston's own and most textbook defaults; 0.2 for SES, a common default for
that method), not optimized per series. Per-series alpha optimization is a
reasonable enhancement but is not implemented here -- it would risk
overfitting on the short series this fixture and even the development-scope
real data can produce, and is not needed to answer this phase's justification
question (whether the *method family* helps, not whether it's been tuned).
"""

from __future__ import annotations

DEFAULT_SES_ALPHA = 0.2
DEFAULT_CROSTON_ALPHA = 0.1


def ses_forecast(history: list[float], horizon: int, alpha: float = DEFAULT_SES_ALPHA) -> list[float]:
    """Simple Exponential Smoothing: one smoothed level, flat forecast.

    Included as the comparison point for what happens when a single level
    is smoothed over a series that mixes zero and nonzero periods (see
    module docstring) -- not expected to be competitive on intermittent
    series.
    """
    if not history:
        raise ValueError("ses_forecast requires at least one historical observation")
    if not (0 < alpha <= 1):
        raise ValueError("alpha must be in (0, 1]")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")

    level = history[0]
    for y in history[1:]:
        level = alpha * y + (1 - alpha) * level
    return [level] * horizon


def croston_forecast(
    history: list[float], horizon: int, alpha: float = DEFAULT_CROSTON_ALPHA, variant: str = "croston"
) -> list[float]:
    """Croston's method (variant="croston") or its SBA bias correction
    (variant="sba"): smooths nonzero demand *size* and the *interval*
    between nonzero observations separately, then forecasts a flat rate =
    smoothed size / smoothed interval.

    [DECISION] the first nonzero observation initializes both the size and
    interval estimates directly (no smoothing applied to the very first
    point) -- one standard, defensible initialization; others exist in the
    literature and would shift early-history forecasts slightly.

    Returns a flat (constant-across-horizon) forecast, like SES -- Croston's
    method does not model trend or seasonality, only demand size and
    frequency.
    """
    if not history:
        raise ValueError("croston_forecast requires at least one historical observation")
    if not (0 < alpha <= 1):
        raise ValueError("alpha must be in (0, 1]")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if variant not in ("croston", "sba"):
        raise ValueError("variant must be 'croston' or 'sba'")

    z_hat: float | None = None  # smoothed nonzero demand size
    p_hat: float | None = None  # smoothed inter-demand interval
    periods_since_last_demand = 0

    for y in history:
        periods_since_last_demand += 1
        if y != 0:
            if z_hat is None:
                z_hat = y
                p_hat = float(periods_since_last_demand)
            else:
                z_hat = alpha * y + (1 - alpha) * z_hat
                p_hat = alpha * periods_since_last_demand + (1 - alpha) * p_hat
            periods_since_last_demand = 0

    if z_hat is None:
        # No nonzero demand ever observed in this history -- no basis for a
        # positive forecast; zero is the only defensible answer.
        return [0.0] * horizon

    rate = z_hat / p_hat
    if variant == "sba":
        rate *= 1 - alpha / 2  # Syntetos-Boylan bias correction
    return [rate] * horizon
