"""Phase 04 — Exploratory Demand Analysis.

Analyzes demand patterns using only the dimensions the Favorita dataset
actually supports (SKUs, hubs, categories, campaigns/promotions, seasonal
events), against the Phase 03 warehouse. Pricing (M-1e) is not analyzed
here at all -- no pricing data exists in this dataset (ADR 0001 D2); that
absence is a documented limitation, not something to approximate.

Every function takes an open DuckDB connection to an already-built
warehouse (demandflow.transform.build_warehouse) and returns plain,
JSON-serializable Python structures -- so the whole result can be written
to reports/phase04/eda_summary.json and rendered into a Markdown report by
demandflow.reporting.generate_eda_report, the same pattern as every
previous phase.
"""

from __future__ import annotations

import datetime
import statistics
from typing import Any

import duckdb

# Syntetos-Boylan-Croston intermittent-demand classification thresholds.
# [DECISION] the conventional literature values, not a JD figure.
ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49

# [DECISION] ABC classification cut points on cumulative share of volume.
ABC_A_CUTOFF = 0.80
ABC_B_CUTOFF = 0.95

# [DECISION] a day's network-wide total is flagged as an anomaly if it is
# more than this many standard deviations from the series mean. Not a JD
# figure; a conventional statistical screening threshold.
ANOMALY_Z_THRESHOLD = 2.0


def _rows_as_dicts(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursor = con.execute(sql)
    columns = [d[0] for d in cursor.description]
    return [_jsonify_row(dict(zip(columns, row))) for row in cursor.fetchall()]


def _jsonify(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, float) and (value != value):  # NaN
        return None
    return value


def _jsonify_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonify(v) for k, v in row.items()}


# --- SKU: velocity, ABC classification, intermittency -----------------------


def sku_velocity_and_intermittency(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = _rows_as_dicts(
        con,
        """
        WITH item_totals AS (
            SELECT
                item_nbr,
                SUM(unit_sales) AS total_unit_sales,
                COUNT(*) AS active_days,
                SUM(CASE WHEN is_imputed_zero THEN 1 ELSE 0 END) AS zero_days,
                COUNT(*) - SUM(CASE WHEN is_imputed_zero THEN 1 ELSE 0 END) AS nonzero_days,
                AVG(CASE WHEN unit_sales > 0 THEN unit_sales END) AS mean_nonzero_demand,
                STDDEV_SAMP(CASE WHEN unit_sales > 0 THEN unit_sales END) AS std_nonzero_demand
            FROM fct_sales_daily
            GROUP BY item_nbr
        )
        SELECT
            item_nbr, total_unit_sales, active_days, zero_days, nonzero_days,
            active_days::DOUBLE / NULLIF(nonzero_days, 0) AS adi,
            POWER(COALESCE(std_nonzero_demand, 0) / NULLIF(mean_nonzero_demand, 0), 2) AS cv_squared,
            SUM(total_unit_sales) OVER () AS grand_total,
            SUM(total_unit_sales) OVER (
                ORDER BY total_unit_sales DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_total
        FROM item_totals
        ORDER BY total_unit_sales DESC
        """,
    )
    for r in rows:
        grand_total = r.pop("grand_total") or 0
        running_total = r.pop("running_total") or 0
        cumulative_share = running_total / grand_total if grand_total else 0.0
        r["cumulative_share_of_volume"] = cumulative_share
        r["abc_class"] = (
            "A" if cumulative_share <= ABC_A_CUTOFF
            else "B" if cumulative_share <= ABC_B_CUTOFF
            else "C"
        )
        adi, cv2 = r.get("adi"), r.get("cv_squared")
        if adi is None or cv2 is None:
            r["intermittency_class"] = "insufficient_data"
        elif adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
            r["intermittency_class"] = "smooth"
        elif adi >= ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
            r["intermittency_class"] = "intermittent"
        elif adi < ADI_THRESHOLD and cv2 >= CV2_THRESHOLD:
            r["intermittency_class"] = "erratic"
        else:
            r["intermittency_class"] = "lumpy"
    return rows


# --- Hub (store) summary -----------------------------------------------------


def hub_summary(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows_as_dicts(
        con,
        """
        SELECT
            h.store_nbr, h.city, h.state, h.store_type, h.cluster,
            COALESCE(SUM(f.unit_sales), 0) AS total_unit_sales,
            COUNT(DISTINCT f.item_nbr) AS distinct_items_sold,
            COALESCE(AVG(f.unit_sales), 0) AS avg_daily_unit_sales
        FROM dim_hub h
        LEFT JOIN fct_sales_daily f ON f.store_nbr = h.store_nbr
        GROUP BY h.store_nbr, h.city, h.state, h.store_type, h.cluster
        ORDER BY total_unit_sales DESC
        """,
    )


# --- Category (family / perishable) summary ---------------------------------


def category_summary(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows_as_dicts(
        con,
        """
        SELECT
            s.family, s.perishable,
            SUM(f.unit_sales) AS total_unit_sales,
            COUNT(DISTINCT f.item_nbr) AS distinct_items,
            AVG(f.unit_sales) AS avg_unit_sales_per_row
        FROM dim_sku s
        JOIN fct_sales_daily f ON f.item_nbr = s.item_nbr
        GROUP BY s.family, s.perishable
        ORDER BY total_unit_sales DESC
        """,
    )


# --- Campaign (promotion) effect --------------------------------------------


def promotion_effect(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Compares avg unit_sales on promoted vs. not-promoted days.

    Uses stg_sales (real observed rows only), not the dense fct table --
    the dense table's onpromotion_filled defaults imputed/unknown days to
    False, which would silently blend "confirmed not promoted" with
    "unknown" into the same bucket. Rows with NULL onpromotion
    (is_promotion_unknown) are excluded from this comparison entirely, and
    returns are excluded (a returned unit isn't demand).
    """
    by_status = _rows_as_dicts(
        con,
        """
        SELECT onpromotion, COUNT(*) AS n, AVG(unit_sales) AS avg_unit_sales,
               STDDEV_SAMP(unit_sales) AS std_unit_sales
        FROM stg_sales
        WHERE onpromotion IS NOT NULL AND NOT is_return
        GROUP BY onpromotion
        ORDER BY onpromotion
        """,
    )
    (excluded_unknown,) = con.execute(
        "SELECT COUNT(*) FROM stg_sales WHERE is_promotion_unknown"
    ).fetchone()
    (excluded_returns,) = con.execute(
        "SELECT COUNT(*) FROM stg_sales WHERE is_return"
    ).fetchone()

    promoted = next((r for r in by_status if r["onpromotion"]), None)
    not_promoted = next((r for r in by_status if not r["onpromotion"]), None)
    uplift_pct = None
    if promoted and not_promoted and not_promoted["avg_unit_sales"]:
        uplift_pct = (promoted["avg_unit_sales"] / not_promoted["avg_unit_sales"]) - 1

    return {
        "by_promotion_status": by_status,
        "rows_excluded_unknown_promotion": excluded_unknown,
        "rows_excluded_returns": excluded_returns,
        "uplift_pct_promoted_vs_not": uplift_pct,
    }


# --- Seasonal events: holidays, day-of-week, payday --------------------------


def seasonal_event_effect(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Joins real sales rows to the resolved per-store calendar (holidays,
    day-of-week, payday). Returns are excluded (not demand); imputed/dense
    rows are excluded (a filled zero has no real calendar-effect signal).
    """
    holiday_effect = _rows_as_dicts(
        con,
        """
        SELECT c.is_holiday, COUNT(*) AS n, AVG(s.unit_sales) AS avg_unit_sales
        FROM stg_sales s
        JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE NOT s.is_return
        GROUP BY c.is_holiday
        ORDER BY c.is_holiday
        """,
    )
    day_of_week = _rows_as_dicts(
        con,
        """
        SELECT c.day_of_week, COUNT(*) AS n, AVG(s.unit_sales) AS avg_unit_sales
        FROM stg_sales s
        JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE NOT s.is_return
        GROUP BY c.day_of_week
        ORDER BY c.day_of_week
        """,
    )
    payday_effect = _rows_as_dicts(
        con,
        """
        SELECT c.is_payday, COUNT(*) AS n, AVG(s.unit_sales) AS avg_unit_sales
        FROM stg_sales s
        JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE NOT s.is_return
        GROUP BY c.is_payday
        ORDER BY c.is_payday
        """,
    )
    return {
        "holiday_effect": holiday_effect,
        "day_of_week": day_of_week,
        "payday_effect": payday_effect,
    }


# --- Trend --------------------------------------------------------------------


def trend_summary(con: duckdb.DuckDBPyConnection, rolling_window: int = 7) -> dict[str, Any]:
    """Network-wide daily total (dense, includes imputed zeros -- a true
    daily total needs every active series represented, not just the days
    each item happened to have a real observation) plus a simple rolling
    mean and an ordinary-least-squares slope over the whole window.

    `rolling_window` defaults to 7 (a calendar week); on a short window (as
    on the fixture) it is reduced so at least 3 points contribute -- the
    real dataset's ~4.6 years won't need this fallback.
    """
    daily = _rows_as_dicts(
        con,
        """
        SELECT date, SUM(unit_sales) AS total_unit_sales, COUNT(*) AS active_series_count
        FROM fct_sales_daily
        GROUP BY date
        ORDER BY date
        """,
    )
    n = len(daily)
    window = rolling_window if n >= rolling_window * 2 else max(1, min(3, n))
    totals = [row["total_unit_sales"] for row in daily]

    rolling_means: list[float | None] = []
    for i in range(n):
        lo = max(0, i - window + 1)
        chunk = totals[lo : i + 1]
        rolling_means.append(sum(chunk) / len(chunk) if len(chunk) == window or i >= window - 1 else None)
    for i, row in enumerate(daily):
        row["rolling_mean"] = rolling_means[i]

    slope = None
    intercept = None
    if n >= 2:
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(totals) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom:
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, totals)) / denom
            intercept = mean_y - slope * mean_x

    return {
        "daily_totals": daily,
        "rolling_window_used": window,
        "ols_slope_per_day": slope,
        "ols_intercept": intercept,
        "trend_direction": (
            "insufficient_data" if slope is None
            else "increasing" if slope > 0
            else "decreasing" if slope < 0
            else "flat"
        ),
    }


# --- Outliers with business context, and network-wide anomalies -------------


def extreme_value_context(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Every DQ-flagged return or extreme value (Phase 02/03), cross-referenced
    with promotion and holiday context -- the "investigate flagged points
    using business context" step Phase 02 explicitly deferred to this phase.
    Does not conclude causation; it only reports what coincides.
    """
    return _rows_as_dicts(
        con,
        """
        SELECT
            s.id, s.date, s.store_nbr, s.item_nbr, s.unit_sales,
            s.is_return, s.is_extreme_value, s.onpromotion,
            c.is_holiday, c.is_payday
        FROM stg_sales s
        LEFT JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE s.is_return OR s.is_extreme_value
        ORDER BY s.date
        """,
    )


def network_anomalies(daily_totals: list[dict[str, Any]], z_threshold: float = ANOMALY_Z_THRESHOLD) -> list[dict[str, Any]]:
    """Flags network-wide days whose total deviates > z_threshold standard
    deviations from the whole series' mean -- a coarse, whole-series
    screen (not the per-item Phase 02 IQR fence, and not yet the more
    careful per-segment anomaly work a later phase might add).
    """
    totals = [row["total_unit_sales"] for row in daily_totals]
    if len(totals) < 2:
        return []
    mean = statistics.mean(totals)
    std = statistics.stdev(totals)
    if std == 0:
        return []
    anomalies = []
    for row in daily_totals:
        z = (row["total_unit_sales"] - mean) / std
        if abs(z) > z_threshold:
            anomalies.append({"date": row["date"], "total_unit_sales": row["total_unit_sales"], "z_score": z})
    return anomalies


# --- Orchestration ------------------------------------------------------------


def run_full_eda(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    trend = trend_summary(con)
    return {
        "sku": sku_velocity_and_intermittency(con),
        "hubs": hub_summary(con),
        "categories": category_summary(con),
        "promotion_effect": promotion_effect(con),
        "seasonal_events": seasonal_event_effect(con),
        "trend": trend,
        "extreme_value_context": extreme_value_context(con),
        "network_anomalies": network_anomalies(trend["daily_totals"]),
        "pricing": {
            "analyzed": False,
            "reason": "No item-level pricing exists in this dataset (ADR 0001 D2). "
            "Not approximated or fabricated.",
        },
    }
