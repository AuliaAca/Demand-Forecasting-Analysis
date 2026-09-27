"""Phase 09 -- Root Cause Analysis, Part A: data issues.

Phase 02's `rule_extreme_values` finding makes an explicit promise this
module fulfills: "Phase 04 (demand analysis) and Phase 09 (RCA) investigate
flagged points using business context -- promotions, holidays, known
events -- before any modeling decision is made about them." Phase 04's
`extreme_value_context()` already gathers that context (promotion/holiday
status alongside every flagged row); this module is the part that was
deliberately deferred to Phase 09 -- turning that gathered context into an
actual evidence-based conclusion, with a baseline to compare against and a
fixed set of sentence templates so no statement here can overstate what the
data shows (CLAUDE.md Section 13).

Scope: the two DQ rules that flag individual, inspectable ROWS (R5 negative
values / returns, R6 extreme values). The other six Phase 02 rules describe
structural or grain-level issues (duplicate keys, null keys, orphan
references, missing calendar dates, missing promotion flags, missing
pricing) that do not have a "which specific rows, and what business context
explains them" shape -- investigating those is either already done
(Phase 02/03's handling decisions) or belongs to a monitoring/tracker phase
(Phase 02's own missing-calendar-dates rule explicitly routes unexplained
gaps to "the Phase 11 discrepancy tracker", not here).
"""

from __future__ import annotations

from typing import Any

import duckdb

# [DECISION] a flagged-row rate at least this many times the baseline rate
# is called "associated with" -- the same screening-threshold discipline as
# Phase 08's WEAK_SEGMENT_WAPE_RATIO, not a JD figure.
ASSOCIATION_LIFT_THRESHOLD = 1.5
MIN_EVIDENCE_N = 5


def load_flagged_rows_with_context(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Every Phase 02/03 return- or extreme-value-flagged row (the same
    population Phase 04's extreme_value_context() inspects), extended with
    item family and store type -- the dimension context this module's
    concentration analysis needs that Phase 04's version didn't carry.

    LEFT JOINs to dim_sku/dim_hub, not INNER: an orphan-item or
    orphan-store row (Phase 02 R3) can be flagged here too, and dropping it
    via an inner join would silently exclude exactly the kind of row
    CLAUDE.md Section 12 says never to silently drop. Such rows fall into
    the "UNKNOWN_ITEM" / "UNKNOWN_STORE" bucket instead.
    """
    cursor = con.execute(
        """
        SELECT
            s.id, s.date, s.store_nbr, s.item_nbr, s.unit_sales,
            s.is_return, s.is_extreme_value, s.onpromotion,
            COALESCE(sku.family, 'UNKNOWN_ITEM') AS item_family,
            COALESCE(hub.store_type, 'UNKNOWN_STORE') AS store_type,
            c.is_holiday, c.is_payday
        FROM stg_sales s
        LEFT JOIN dim_sku sku ON sku.item_nbr = s.item_nbr
        LEFT JOIN dim_hub hub ON hub.store_nbr = s.store_nbr
        LEFT JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE s.is_return OR s.is_extreme_value
        ORDER BY s.date
        """
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_baseline_rates(con: duckdb.DuckDBPyConnection) -> dict[str, float | None]:
    """Network-wide promotion/holiday rates across every real (non-return)
    sales row -- the denominator a flagged-row population's own rate is
    compared against. Mirrors Phase 04's promotion_effect()/
    seasonal_event_effect() exclusion rules (unknown-promotion rows
    excluded, returns excluded) so the comparison is apples-to-apples with
    that phase's own numbers, not a differently-scoped baseline.
    """
    (promotion_rate,) = con.execute(
        """
        SELECT AVG(CASE WHEN onpromotion THEN 1.0 ELSE 0.0 END)
        FROM stg_sales WHERE onpromotion IS NOT NULL AND NOT is_return
        """
    ).fetchone()
    (holiday_rate,) = con.execute(
        """
        SELECT AVG(CASE WHEN c.is_holiday THEN 1.0 ELSE 0.0 END)
        FROM stg_sales s
        JOIN int_calendar_by_store c ON c.store_nbr = s.store_nbr AND c.date = s.date
        WHERE NOT s.is_return
        """
    ).fetchone()
    return {"promotion_rate": promotion_rate, "holiday_rate": holiday_rate}


def _rate(rows: list[dict], predicate) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if predicate(r)) / len(rows)


def _counts_by(rows: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r[key]] = counts.get(r[key], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def gather_data_issue_evidence(flagged_rows: list[dict[str, Any]], baseline: dict[str, float | None]) -> dict[str, Any]:
    """Splits the flagged population into returns and extreme values (a row
    can be both), then computes each population's promotion/holiday
    coincidence rate against the network-wide baseline, plus which item
    families and store types the population concentrates in.
    """
    evidence: dict[str, Any] = {}
    for label, predicate in [
        ("returns", lambda r: r["is_return"]),
        ("extreme_values", lambda r: r["is_extreme_value"]),
    ]:
        population = [r for r in flagged_rows if predicate(r)]
        n = len(population)
        promotion_rate = _rate(population, lambda r: r["onpromotion"] is True)
        holiday_rate = _rate(population, lambda r: bool(r["is_holiday"]))
        evidence[label] = {
            "n": n,
            "promotion_rate": promotion_rate,
            "holiday_rate": holiday_rate,
            "promotion_lift": (promotion_rate / baseline["promotion_rate"])
            if promotion_rate is not None and baseline["promotion_rate"] else None,
            "holiday_lift": (holiday_rate / baseline["holiday_rate"])
            if holiday_rate is not None and baseline["holiday_rate"] else None,
            "by_item_family": _counts_by(population, "item_family"),
            "by_store_type": _counts_by(population, "store_type"),
        }
    evidence["baseline"] = baseline
    return evidence


def _lift_statement(label: str, lift_name: str, rate: float | None, lift: float | None, n: int, baseline_rate: float | None) -> str | None:
    if rate is None or lift is None or baseline_rate is None or n < MIN_EVIDENCE_N:
        return None
    if lift >= ASSOCIATION_LIFT_THRESHOLD:
        return (
            f"{label} coincide with {lift_name} at a rate of {rate:.1%} (n={n}), "
            f"{lift:.1f}x the network-wide baseline rate of {baseline_rate:.1%} -- "
            f"associated with {lift_name}, a possible contributor, not a confirmed cause."
        )
    return None


def build_data_issue_rca(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Turns gathered evidence into RCA records -- one per flagged-row
    population, each stating what was found (and, honestly, when nothing
    in this dataset explains the pattern) using only CLAUDE.md Section 13's
    evidence vocabulary."""
    records: list[dict[str, Any]] = []
    baseline = evidence["baseline"]

    for label, lift_label in [("returns", "a promotion day"), ("extreme_values", "a promotion day")]:
        pop = evidence[label]
        if pop["n"] == 0:
            records.append({
                "trigger_type": "data_issue",
                "issue": label,
                "n": 0,
                "candidate_contributors": [],
                "statement": f"No {label.replace('_', ' ')} rows were flagged on this run -- nothing to investigate.",
            })
            continue

        contributors = []
        promo_stmt = _lift_statement(
            label.replace("_", " "), "a promotion day", pop["promotion_rate"], pop["promotion_lift"], pop["n"], baseline["promotion_rate"]
        )
        if promo_stmt:
            contributors.append(promo_stmt)
        holiday_stmt = _lift_statement(
            label.replace("_", " "), "a holiday", pop["holiday_rate"], pop["holiday_lift"], pop["n"], baseline["holiday_rate"]
        )
        if holiday_stmt:
            contributors.append(holiday_stmt)

        # Flagged only when one family holds a disproportionate majority of
        # a population spread across several families -- not when there is
        # effectively only one family to begin with (nothing to conclude
        # from "100% of these rows are in the only family present").
        top_family = next(iter(pop["by_item_family"]), None)
        if top_family and len(pop["by_item_family"]) > 1 and pop["n"] >= MIN_EVIDENCE_N:
            top_family_share = pop["by_item_family"][top_family] / pop["n"]
            if top_family_share >= 0.5:
                contributors.append(
                    f"{label.replace('_', ' ')} concentrate in item_family={top_family} "
                    f"({top_family_share:.0%} of {pop['n']} flagged rows) -- associated with "
                    f"that category, requires further investigation to say why."
                )

        if not contributors:
            statement = (
                f"{pop['n']} {label.replace('_', ' ')} row(s) were flagged. No elevated "
                "promotion or holiday coincidence, and no single item family or store type "
                "dominates the population -- this dataset's available business context does "
                "not explain the pattern; cause unknown from available evidence, requires "
                "further investigation with inputs not present here (e.g. a stockout or "
                "data-entry-audit signal)."
            )
        else:
            statement = (
                f"{pop['n']} {label.replace('_', ' ')} row(s) were flagged. " + " ".join(contributors)
            )

        records.append({
            "trigger_type": "data_issue",
            "issue": label,
            "n": pop["n"],
            "promotion_rate": pop["promotion_rate"],
            "promotion_lift": pop["promotion_lift"],
            "holiday_rate": pop["holiday_rate"],
            "holiday_lift": pop["holiday_lift"],
            "by_item_family": pop["by_item_family"],
            "by_store_type": pop["by_store_type"],
            "candidate_contributors": contributors,
            "statement": statement,
        })
    return records
