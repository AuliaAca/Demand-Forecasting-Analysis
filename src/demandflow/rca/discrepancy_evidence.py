"""Phase 09 -- Root Cause Analysis, Part B: forecast discrepancies.

CLAUDE.md Section 13: "A forecast discrepancy or anomaly is an
investigation trigger." Phase 08 already found and structured the
triggers -- its `weak_segment`, `systematic_bias`, and
`segment_champion_switch` findings each name a specific (dimension,
segment, model) combination where accuracy is worse than the network as a
whole. This module is the "why might this be happening" step: for each
trigger, it gathers two kinds of reproducible evidence and states,
honestly, what the data does and does not explain.

Evidence gathered:
1. **Demand trend divergence** -- a lag-based model (Naive, Seasonal
   Naive, SES) cannot adapt to a trend mid-window; if a segment's own
   demand trend differs materially from the network-wide trend, that is
   consistent with (not proof of) the segment's forecast bias. Computed
   only for the four "population" dimensions (item_family, store_type,
   cluster, intermittency_class) -- a fixed set of items/stores with their
   own independent history. Not computed for promotion/holiday/payday/
   horizon_step/as_of_date, which describe a row's calendar or schedule
   context, not a population with its own trend.
2. **DQ-flag coincidence** -- whether the specific (store, item,
   target_date) rows behind a discrepancy show an elevated rate of Phase
   02/03's is_extreme_value / is_return / is_imputed_zero flags versus the
   network-wide baseline across every scored forecast row. Computed for
   every dimension, since it only needs the row-level flags Phase 08's
   `load_scored_forecasts_with_context()` already carries -- no per-
   dimension SQL required.
"""

from __future__ import annotations

from typing import Any

import duckdb

from demandflow.evaluation.segment_evaluation import SEGMENT_KEY_FUNCTIONS

# [DECISION] same screening-threshold discipline as Phase 08 and RCA Part A.
DQ_FLAG_LIFT_THRESHOLD = 1.5
MIN_EVIDENCE_N = 5
# a segment trend is called "diverging" from the network trend when the two
# slopes differ in sign, or the segment's magnitude is at least this many
# times the network's -- a coarse, documented heuristic, not a JD figure.
TREND_DIVERGENCE_MAGNITUDE_RATIO = 2.0

POPULATION_DIMENSIONS = {"item_family", "store_type", "cluster", "intermittency_class"}
_SEGMENT_FILTER_SQL = {
    "item_family": "sku.family = ?",
    "store_type": "hub.store_type = ?",
    "cluster": "CAST(hub.cluster AS VARCHAR) = ?",
}


def rows_for_segment(
    scored_rows: list[dict[str, Any]],
    dimension: str,
    segment_value: str,
    item_to_intermittency_class: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """The exact scored-forecast rows Phase 08 grouped into
    (dimension, segment_value) -- reuses SEGMENT_KEY_FUNCTIONS rather than
    re-deriving segment membership independently, so this can never
    silently disagree with what Phase 08 actually reported."""
    if dimension == "intermittency_class":
        if not item_to_intermittency_class:
            return []
        return [r for r in scored_rows if item_to_intermittency_class.get(r["item_nbr"]) == segment_value]
    key_fn = SEGMENT_KEY_FUNCTIONS.get(dimension)
    if key_fn is None:
        return []
    return [r for r in scored_rows if str(key_fn(r)) == segment_value]


def unique_triples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per distinct (store_nbr, item_nbr, target_date).

    `scored_rows` (from Phase 08's load_scored_forecasts_with_context) has
    one row per (as_of_date, horizon_step, target_date, store_nbr,
    item_nbr, MODEL) -- so the same underlying sales day can appear 4 or 5
    times (Seasonal Naive is skipped when a series has too little history
    for the season length; the other four models are not), and the same
    target_date can also be reached from more than one as-of/horizon
    origin. A DQ flag belongs to the (store, item, target_date) triple
    itself, not to how many models or backtest origins happened to score
    it, so evidence about that flag's rate must be computed over distinct
    triples -- otherwise a triple reached by more models, or by more
    as-of/horizon origins, would be silently overweighted.
    """
    seen: set[tuple] = set()
    result = []
    for r in rows:
        key = (r["store_nbr"], r["item_nbr"], r["target_date"])
        if key not in seen:
            seen.add(key)
            result.append(r)
    return result


def dq_flag_rates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rates over the distinct (store, item, target_date) triples in `rows`
    -- callers pass either a full population or an already-filtered
    segment; deduplication happens here so every caller gets it for free."""
    rows = unique_triples(rows)
    n = len(rows)
    if n == 0:
        return {"n": 0, "extreme_value_rate": None, "return_rate": None, "imputed_zero_rate": None}
    return {
        "n": n,
        "extreme_value_rate": sum(1 for r in rows if r["target_is_extreme_value"]) / n,
        "return_rate": sum(1 for r in rows if r["target_is_return"]) / n,
        "imputed_zero_rate": sum(1 for r in rows if r["target_is_imputed_zero"]) / n,
    }


def _ols_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if not denom:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom


def network_trend_slope(con: duckdb.DuckDBPyConnection) -> float | None:
    """Reuses Phase 04's trend_summary() OLS slope as the network-wide
    baseline a segment's own trend is compared against, rather than
    recomputing a different trend definition here."""
    from demandflow.analysis.eda import trend_summary

    return trend_summary(con)["ols_slope_per_day"]


def segment_trend_slope(
    con: duckdb.DuckDBPyConnection,
    dimension: str,
    segment_value: str,
    item_nbrs: list[int] | None = None,
) -> float | None:
    """OLS slope of daily total demand restricted to one Phase 08 segment's
    own items/stores -- only for the four population dimensions; returns
    None for a row-context dimension (promotion/holiday/payday/horizon_step/
    as_of_date), where "this segment's demand trend" isn't a meaningful
    question (see module docstring).
    """
    if dimension == "intermittency_class":
        if not item_nbrs:
            return None
        placeholders = ",".join("?" for _ in item_nbrs)
        rows = con.execute(
            f"SELECT date, SUM(unit_sales) FROM fct_sales_daily WHERE item_nbr IN ({placeholders}) GROUP BY date ORDER BY date",
            item_nbrs,
        ).fetchall()
    elif dimension in _SEGMENT_FILTER_SQL:
        rows = con.execute(
            f"""
            SELECT f.date, SUM(f.unit_sales)
            FROM fct_sales_daily f
            JOIN dim_sku sku ON sku.item_nbr = f.item_nbr
            JOIN dim_hub hub ON hub.store_nbr = f.store_nbr
            WHERE {_SEGMENT_FILTER_SQL[dimension]}
            GROUP BY f.date ORDER BY f.date
            """,
            [segment_value],
        ).fetchall()
    else:
        return None

    xs = list(range(len(rows)))
    ys = [r[1] for r in rows]
    return _ols_slope(xs, ys)


def gather_discrepancy_evidence(
    con: duckdb.DuckDBPyConnection,
    finding: dict[str, Any],
    scored_rows: list[dict[str, Any]],
    baseline_dq_rates: dict[str, Any],
    network_trend: float | None,
    item_to_intermittency_class: dict[int, str] | None = None,
) -> dict[str, Any]:
    dimension = finding["dimension"]
    segment = finding["segment"]
    segment_rows = rows_for_segment(scored_rows, dimension, segment, item_to_intermittency_class)

    item_nbrs = None
    if dimension == "intermittency_class" and item_to_intermittency_class:
        item_nbrs = [item for item, cls in item_to_intermittency_class.items() if cls == segment]

    return {
        "dimension": dimension,
        "segment": segment,
        "dq_flag_rates": dq_flag_rates(segment_rows),
        "baseline_dq_flag_rates": baseline_dq_rates,
        "segment_trend_slope": (
            segment_trend_slope(con, dimension, segment, item_nbrs) if dimension in POPULATION_DIMENSIONS else None
        ),
        "network_trend_slope": network_trend,
    }


def _dq_flag_statement(evidence: dict[str, Any]) -> str | None:
    seg, base = evidence["dq_flag_rates"], evidence["baseline_dq_flag_rates"]
    if seg["n"] < MIN_EVIDENCE_N:
        return None
    flagged = []
    for label, key in [("extreme values", "extreme_value_rate"), ("returns", "return_rate"), ("imputed (zero) days", "imputed_zero_rate")]:
        seg_rate, base_rate = seg.get(key), base.get(key)
        if seg_rate is None or not base_rate:
            continue
        lift = seg_rate / base_rate
        if lift >= DQ_FLAG_LIFT_THRESHOLD:
            flagged.append(f"{label} at {lift:.1f}x the network-wide rate ({seg_rate:.1%} vs {base_rate:.1%})")
    if not flagged:
        return None
    return (
        "The rows behind this discrepancy show an elevated rate of " + "; ".join(flagged) +
        " -- associated with this discrepancy, a possible contributor, not a confirmed cause."
    )


def _trend_statement(evidence: dict[str, Any]) -> str | None:
    seg_slope, net_slope = evidence["segment_trend_slope"], evidence["network_trend_slope"]
    if seg_slope is None or net_slope is None:
        return None
    diverges = (seg_slope * net_slope < 0) or (
        net_slope != 0 and abs(seg_slope) >= TREND_DIVERGENCE_MAGNITUDE_RATIO * abs(net_slope)
    )
    if not diverges:
        return None
    return (
        f"This segment's own demand trend ({seg_slope:+.2f} units/day) diverges from the "
        f"network-wide trend ({net_slope:+.2f} units/day) -- consistent with a lag-based "
        "model (which repeats a recent observed value rather than adapting to a trend) "
        "systematically mis-forecasting this segment, though this does not by itself "
        "confirm the trend is the cause."
    )


def build_discrepancy_rca(finding: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    contributors = [s for s in (_trend_statement(evidence), _dq_flag_statement(evidence)) if s]
    if contributors:
        statement = " ".join(contributors)
    else:
        statement = (
            "No elevated DQ-flag coincidence and no diverging demand trend was found for "
            "this segment in this dataset -- the available evidence does not explain this "
            f"discrepancy ({finding['dimension']}={finding['segment']}); cause unknown from "
            "available evidence, requires further investigation with inputs not present "
            "here (e.g. a stockout signal, competitor activity, or local events)."
        )
    return {
        "trigger_type": "forecast_discrepancy",
        "source_finding_category": finding["category"],
        "dimension": finding["dimension"],
        "segment": finding["segment"],
        "model": finding.get("model") or finding.get("recommended_model"),
        "trigger_statement": finding["statement"],
        "evidence": evidence,
        "candidate_contributors": contributors,
        "statement": statement,
    }
