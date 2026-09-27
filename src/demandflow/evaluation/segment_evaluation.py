"""Phase 08 -- Forecast Evaluation: rigorous, multi-dimension accuracy analysis.

Phase 04 analyzed DEMAND across the JD's explicit dimensions (SKU, hub,
category, campaign, seasonal event -- pricing excluded, since no pricing
data exists in this dataset, ADR 0001 D2). This module asks the matching
question for FORECAST ACCURACY: not "what did demand look like across
these dimensions", but "where is the forecast right, and where is it
weak" -- directly the JD mission "Monitor forecast accuracy and turn
findings into actionable recommendations" (CLAUDE.md Section 3.3).

Scope: evaluates the five models Phase 05/06 backtest with a full
rolling-origin design (Naive, Seasonal Naive, SES, Croston, SBA) -- the
models with as-of-date x horizon-step coverage broad enough to support a
segment/time breakdown. Phase 07's LightGBM model uses a deliberately
different, single-final-holdout design (docs/phase_reports/phase07.md) and
is not folded into this per-segment/per-as-of-date framework: a model
scored at exactly one as-of date has nothing to show on an "accuracy over
time" axis, and mixing it in would misrepresent both results. This is a
documented scope decision (CLAUDE.md Section 18), not an oversight --
Phase 07's headline holdout number is referenced in
docs/forecast_evaluation.md instead.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import duckdb

from demandflow.forecasting.metrics import summarize as summarize_pairs

# [DECISION] heuristic screening thresholds -- conventional choices in the
# same spirit as Phase 04's ANOMALY_Z_THRESHOLD / ABC cutoffs, not JD figures.
WEAK_SEGMENT_WAPE_RATIO = 1.5
MIN_SEGMENT_SCORED_N = 5
SYSTEMATIC_BIAS_THRESHOLD = 0.20
# a segment's champion must beat the overall champion's own WAPE *in that
# segment* by at least this margin to be worth calling out as a switch.
SEGMENT_CHAMPION_IMPROVEMENT_RATIO = 0.95

Row = dict[str, Any]


def load_scored_forecasts_with_context(con: duckdb.DuckDBPyConnection) -> list[Row]:
    """One row per scored fct_forecast record, joined with the dimension
    context every breakdown below needs: SKU family (category), hub
    store_type/cluster, the target date's promotion/holiday/payday status
    -- the same JD dimensions Phase 04 analyzed for demand, now carried
    alongside each forecast's error -- and the target date's own DQ flags
    (extreme value, return, imputed zero), which this module doesn't use
    itself but Phase 09's root-cause analysis does, to check whether a
    forecast discrepancy coincides with a data-quality issue rather than
    recomputing the same join there.

    Every is_scored row's target_date falls inside its series' observed
    active window (backtest.py's contract), which is itself inside
    stg_sales' global date range -- the same range int_calendar_by_store is
    built over -- so the calendar join is always complete here; only the
    promotion join can be genuinely unknown (raw source nulls), which is
    why it is tracked with its own flag rather than defaulted silently.
    """
    cursor = con.execute(
        """
        SELECT
            f.as_of_date, f.horizon_step, f.target_date, f.store_nbr, f.item_nbr,
            f.model, f.forecast, f.actual,
            sku.family AS item_family,
            hub.store_type AS store_type,
            hub.cluster AS cluster,
            COALESCE(sd.onpromotion_filled, FALSE) AS target_onpromotion,
            COALESCE(sd.is_promotion_unknown, TRUE) AS target_promotion_unknown,
            COALESCE(cal.is_holiday, FALSE) AS target_is_holiday,
            COALESCE(cal.is_payday, FALSE) AS target_is_payday,
            COALESCE(sd.is_extreme_value, FALSE) AS target_is_extreme_value,
            COALESCE(sd.is_return, FALSE) AS target_is_return,
            COALESCE(sd.is_imputed_zero, FALSE) AS target_is_imputed_zero
        FROM fct_forecast f
        JOIN dim_sku sku ON sku.item_nbr = f.item_nbr
        JOIN dim_hub hub ON hub.store_nbr = f.store_nbr
        LEFT JOIN fct_sales_daily sd
            ON sd.store_nbr = f.store_nbr AND sd.item_nbr = f.item_nbr AND sd.date = f.target_date
        LEFT JOIN int_calendar_by_store cal
            ON cal.store_nbr = f.store_nbr AND cal.date = f.target_date
        WHERE f.is_scored
        """
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _pairs_by_model(rows: list[Row]) -> dict[str, list[tuple[float, float]]]:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        grouped[r["model"]].append((r["actual"], r["forecast"]))
    return grouped


def _sort_key(key: Any) -> tuple[int, Any]:
    return (0, key) if isinstance(key, (int, float)) else (1, str(key))


def evaluate_by_dimension(rows: list[Row], key_fn: Callable[[Row], Any]) -> dict[str, dict[str, dict]]:
    """Generic WAPE/MAE/bias breakdown: groups `rows` by key_fn(row), then by
    model within each group. `key_fn` returning None excludes a row (used
    when a dimension is genuinely unknown for that record, e.g. an
    unresolved promotion flag) rather than inventing an "unknown" bucket
    that would blend genuinely different situations together.
    """
    groups: dict[Any, list[Row]] = defaultdict(list)
    for r in rows:
        key = key_fn(r)
        if key is None:
            continue
        groups[key].append(r)

    result: dict[str, dict[str, dict]] = {}
    for key in sorted(groups, key=_sort_key):
        by_model = _pairs_by_model(groups[key])
        result[str(key)] = {model: summarize_pairs(pairs) for model, pairs in by_model.items()}
    return result


def _horizon_step_key(r: Row) -> Any:
    return r["horizon_step"]


def _as_of_date_key(r: Row) -> Any:
    return r["as_of_date"]


def _item_family_key(r: Row) -> Any:
    return r["item_family"]


def _store_type_key(r: Row) -> Any:
    return r["store_type"]


def _cluster_key(r: Row) -> Any:
    return r["cluster"]


def _promotion_key(r: Row) -> Any:
    """None (excluded) when the target date's promotion status is unknown
    (raw source null), rather than defaulting it into "not_promoted" -- the
    same standard Phase 04's promotion_effect() holds itself to."""
    if r["target_promotion_unknown"]:
        return None
    return "promoted" if r["target_onpromotion"] else "not_promoted"


def _holiday_key(r: Row) -> Any:
    return "holiday" if r["target_is_holiday"] else "non_holiday"


def _payday_key(r: Row) -> Any:
    return "payday" if r["target_is_payday"] else "non_payday"


# Exposed (not just used internally) so Phase 09's root-cause analysis can
# recover exactly which scored-forecast rows belong to a given Phase 08
# segment, without re-deriving or duplicating this grouping logic.
SEGMENT_KEY_FUNCTIONS: dict[str, Callable[[Row], Any]] = {
    "item_family": _item_family_key,
    "store_type": _store_type_key,
    "cluster": _cluster_key,
    "promotion": _promotion_key,
    "holiday": _holiday_key,
    "payday": _payday_key,
    "horizon_step": _horizon_step_key,
    "as_of_date": _as_of_date_key,
}


def evaluate_by_horizon_step(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _horizon_step_key)


def evaluate_by_as_of_date(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _as_of_date_key)


def evaluate_by_item_family(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _item_family_key)


def evaluate_by_store_type(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _store_type_key)


def evaluate_by_cluster(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _cluster_key)


def evaluate_by_promotion(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _promotion_key)


def evaluate_by_holiday(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _holiday_key)


def evaluate_by_payday(rows: list[Row]) -> dict[str, dict[str, dict]]:
    return evaluate_by_dimension(rows, _payday_key)


DIMENSIONS: dict[str, Callable[[list[Row]], dict]] = {
    name: (lambda rows, fn=key_fn: evaluate_by_dimension(rows, fn))
    for name, key_fn in SEGMENT_KEY_FUNCTIONS.items()
}


def evaluate_all_dimensions(rows: list[Row]) -> dict[str, dict]:
    return {name: fn(rows) for name, fn in DIMENSIONS.items()}


def _champion(by_model: dict[str, dict]) -> tuple[str | None, float | None]:
    """Lowest-WAPE model in a segment, restricted to models with at least
    MIN_SEGMENT_SCORED_N scored rows there -- so a 1-row fluke can't be
    crowned champion of a segment."""
    wapes = {
        m: v["wape"] for m, v in by_model.items()
        if v["wape"] is not None and v["n"] >= MIN_SEGMENT_SCORED_N
    }
    if not wapes:
        return None, None
    best = min(wapes, key=wapes.get)
    return best, wapes[best]


def champions_by_dimension(dimension_result: dict[str, dict]) -> dict[str, dict]:
    return {segment: dict(zip(("model", "wape"), _champion(by_model))) for segment, by_model in dimension_result.items()}


def _ols_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if not denom:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom


def accuracy_trend_by_model(by_as_of_date: dict[str, dict[str, dict]]) -> dict[str, dict]:
    """WAPE-over-time slope per model across the as-of dates in the
    rolling-origin schedule -- the same "is this getting worse" question
    Phase 04's trend_summary asks of demand volume, asked here of forecast
    error instead. A positive slope means WAPE rises (accuracy
    deteriorating) as the backtest window moves forward; negative means
    accuracy improving. With as few as-of dates as this project's dev
    scope produces, treat the direction as illustrative, not a robust
    trend estimate (see docs/forecast_evaluation.md).
    """
    as_of_dates = sorted(by_as_of_date)
    models = sorted({m for by_model in by_as_of_date.values() for m in by_model})

    result: dict[str, dict] = {}
    for model in models:
        xs, ys = [], []
        for i, as_of in enumerate(as_of_dates):
            metrics = by_as_of_date[as_of].get(model)
            if metrics and metrics["wape"] is not None:
                xs.append(i)
                ys.append(metrics["wape"])
        slope = _ols_slope(xs, ys)
        result[model] = {
            "points_used": len(xs),
            "wape_ols_slope_per_as_of_step": slope,
            "direction": (
                "insufficient_data" if slope is None
                else "deteriorating" if slope > 0
                else "improving" if slope < 0
                else "flat"
            ),
        }
    return result


# --- Findings: turning the breakdowns above into actionable statements -----


def _weak_segment_findings(
    dimension_name: str, dimension_result: dict[str, dict], overall_by_model: dict, champion_model: str
) -> list[dict]:
    overall_metrics = overall_by_model.get(champion_model)
    if not overall_metrics or overall_metrics["wape"] is None:
        return []
    overall_wape = overall_metrics["wape"]

    findings = []
    for segment, by_model in dimension_result.items():
        metrics = by_model.get(champion_model)
        if not metrics or metrics["wape"] is None or metrics["n"] < MIN_SEGMENT_SCORED_N:
            continue
        ratio = metrics["wape"] / overall_wape if overall_wape else None
        if ratio is None or ratio < WEAK_SEGMENT_WAPE_RATIO:
            continue
        findings.append({
            "category": "weak_segment",
            "dimension": dimension_name,
            "segment": segment,
            "model": champion_model,
            "n": metrics["n"],
            "segment_wape": metrics["wape"],
            "overall_wape": overall_wape,
            "ratio_to_overall": ratio,
            "statement": (
                f"{champion_model}'s error in {dimension_name}={segment} "
                f"(WAPE {metrics['wape']:.3f}, n={metrics['n']}) is associated with "
                f"{ratio:.1f}x the overall WAPE ({overall_wape:.3f}) for this model -- "
                "requires further investigation."
            ),
            "recommendation": (
                f"Review {dimension_name}={segment} before relying on {champion_model}'s "
                "forecasts there; consider a segment-specific model or manual planner "
                "review for this slice."
            ),
        })
    return findings


def _systematic_bias_findings(dimension_name: str, dimension_result: dict[str, dict], champion_model: str) -> list[dict]:
    findings = []
    for segment, by_model in dimension_result.items():
        metrics = by_model.get(champion_model)
        if not metrics or metrics.get("forecast_bias") is None or metrics["n"] < MIN_SEGMENT_SCORED_N:
            continue
        bias = metrics["forecast_bias"]
        if abs(bias) < SYSTEMATIC_BIAS_THRESHOLD:
            continue
        direction = "over-forecasts" if bias > 0 else "under-forecasts"
        risk = (
            "Over-forecasting risks excess inventory and holding cost."
            if bias > 0 else
            "Under-forecasting risks stockouts and unmet demand."
        )
        findings.append({
            "category": "systematic_bias",
            "dimension": dimension_name,
            "segment": segment,
            "model": champion_model,
            "n": metrics["n"],
            "forecast_bias": bias,
            "statement": (
                f"{champion_model} systematically {direction} in {dimension_name}={segment} "
                f"(bias {bias:+.1%} of actual volume, n={metrics['n']})."
            ),
            "recommendation": f"{risk} Flag {dimension_name}={segment} for manual review before relying on this model's forecast there.",
        })
    return findings


def _champion_switch_findings(
    dimension_name: str, dimension_result: dict[str, dict], champions: dict[str, dict], overall_champion_model: str
) -> list[dict]:
    findings = []
    for segment, champ in champions.items():
        model = champ["model"]
        if model is None or model == overall_champion_model:
            continue
        overall_champ_in_segment = dimension_result[segment].get(overall_champion_model)
        if not overall_champ_in_segment or overall_champ_in_segment["wape"] is None:
            continue
        if overall_champ_in_segment["n"] < MIN_SEGMENT_SCORED_N:
            continue
        if champ["wape"] >= overall_champ_in_segment["wape"] * SEGMENT_CHAMPION_IMPROVEMENT_RATIO:
            continue  # not a meaningfully better fit here
        findings.append({
            "category": "segment_champion_switch",
            "dimension": dimension_name,
            "segment": segment,
            "recommended_model": model,
            "recommended_model_wape": champ["wape"],
            "overall_champion_model": overall_champion_model,
            "overall_champion_wape_in_segment": overall_champ_in_segment["wape"],
            "statement": (
                f"In {dimension_name}={segment}, {model} (WAPE {champ['wape']:.3f}) is "
                f"associated with lower error than the overall champion {overall_champion_model} "
                f"(WAPE {overall_champ_in_segment['wape']:.3f} in this segment)."
            ),
            "recommendation": (
                f"Consider using {model} specifically for {dimension_name}={segment} "
                f"instead of applying {overall_champion_model} network-wide."
            ),
        })
    return findings


def _horizon_decay_finding(by_horizon_step: dict[str, dict], champion_model: str) -> dict | None:
    steps = sorted(int(k) for k in by_horizon_step)
    if len(steps) < 2:
        return None
    first, last = steps[0], steps[-1]
    first_metrics = by_horizon_step[str(first)].get(champion_model)
    last_metrics = by_horizon_step[str(last)].get(champion_model)
    if not first_metrics or not last_metrics:
        return None
    if first_metrics["wape"] is None or last_metrics["wape"] is None:
        return None
    if first_metrics["n"] < MIN_SEGMENT_SCORED_N or last_metrics["n"] < MIN_SEGMENT_SCORED_N:
        return None
    if last_metrics["wape"] <= first_metrics["wape"]:
        return None
    return {
        "category": "horizon_decay",
        "dimension": "horizon_step",
        "model": champion_model,
        "first_step": first, "first_step_wape": first_metrics["wape"],
        "last_step": last, "last_step_wape": last_metrics["wape"],
        "statement": (
            f"{champion_model}'s error at horizon step {last} (WAPE {last_metrics['wape']:.3f}) "
            f"is higher than at step {first} (WAPE {first_metrics['wape']:.3f}), consistent with "
            "accuracy decaying the further ahead the forecast reaches."
        ),
        "recommendation": (
            "For decisions that can tolerate it, prefer the shorter end of the horizon, or "
            f"re-forecast more frequently than every {last - first + 1} days, to keep the "
            "effective lead time short."
        ),
    }


def _time_trend_finding(trend_by_model: dict[str, dict], champion_model: str) -> dict | None:
    trend = trend_by_model.get(champion_model)
    if not trend or trend["direction"] != "deteriorating":
        return None
    return {
        "category": "time_trend",
        "dimension": "as_of_date",
        "model": champion_model,
        "points_used": trend["points_used"],
        "wape_ols_slope_per_as_of_step": trend["wape_ols_slope_per_as_of_step"],
        "statement": (
            f"{champion_model}'s WAPE trends upward across this backtest's as-of dates "
            f"(slope {trend['wape_ols_slope_per_as_of_step']:.4f} per step, "
            f"{trend['points_used']} point(s)) -- consistent with accuracy deteriorating "
            "over the window, though with this few points this is illustrative, not a "
            "statistically robust trend."
        ),
        "recommendation": (
            "Track this model's WAPE over time as more as-of dates accumulate (Phase 10 "
            "monitoring) before concluding a real drift exists."
        ),
    }


SEGMENT_DIMENSIONS = ["item_family", "store_type", "cluster", "promotion", "holiday", "payday", "intermittency_class"]


def identify_findings(evaluation: dict, overall_by_model: dict, champion_model: str | None) -> list[dict]:
    """Turns the breakdowns in `evaluation["by_dimension"]` (plus the time
    trend) into a flat list of actionable, evidence-language findings
    (CLAUDE.md Section 13: "associated with", never "caused by").
    """
    if champion_model is None:
        return []

    findings: list[dict] = []
    for dim in SEGMENT_DIMENSIONS:
        dimension_result = evaluation["by_dimension"].get(dim)
        if not dimension_result:
            continue
        findings.extend(_weak_segment_findings(dim, dimension_result, overall_by_model, champion_model))
        findings.extend(_systematic_bias_findings(dim, dimension_result, champion_model))
        champions = champions_by_dimension(dimension_result)
        findings.extend(_champion_switch_findings(dim, dimension_result, champions, champion_model))

    horizon_result = evaluation["by_dimension"].get("horizon_step")
    if horizon_result:
        horizon_finding = _horizon_decay_finding(horizon_result, champion_model)
        if horizon_finding:
            findings.append(horizon_finding)

    time_finding = _time_trend_finding(evaluation.get("accuracy_trend_by_model", {}), champion_model)
    if time_finding:
        findings.append(time_finding)

    return findings
