"""The Phase 02 data-quality rule catalog.

Implements CLAUDE.md §12's documentation contract — every rule below records
**rule, finding, severity, consequence, handling decision** — for the issue
categories PHASE_02.md names: missing dates, duplicates, null/invalid keys,
suspicious values, date gaps, grain problems, and missing JD-relevant
dimensions.

Scope boundary (phase discipline, CLAUDE.md §18): this module *detects and
documents a handling decision*. It does not implement the fix — deduplication,
quarantining rows, flag columns, etc. all happen in the staging layer, which
is Phase 03's job. CLAUDE.md §12 is explicit: "Do not silently remove
problematic records" — every handling decision below either keeps the row
(with a flag) or explicitly quarantines it to a named, inspectable location,
never a silent drop.

Severity is not a single generic row-count-percentage table. Each rule's
severity is justified by what the issue actually does downstream (a comment
inline explains the reasoning), because CLAUDE.md §11 makes the same point
about metrics: choice must be justified by data characteristics and business
use, not applied as fake-precision boilerplate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb

from demandflow.profiling import checks
from demandflow.profiling.checks import scan_expr

# Severity scale, most to least severe. Defined once so every rule uses the
# same vocabulary; what triggers each level is decided per rule, not globally.
CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
INFO = "INFO"
PASS = "PASS"

# [DECISION] thresholds used by more than one rule below, named so their
# reasoning lives in one place instead of being a magic number per rule.
ONPROMOTION_NULL_HIGH_SEVERITY_THRESHOLD = 0.20  # >20% starts to seriously undermine M-1d
EXTREME_VALUE_IQR_MULTIPLIER = 3.0  # a conventional "far outlier" fence, not a JD figure


@dataclass(frozen=True)
class DQFinding:
    rule_id: str
    category: str  # grain | keys | dates | values | dimensions
    description: str
    metrics: dict[str, Any]
    severity: str
    consequence: str
    handling_decision: str


# --- R1: grain duplicates -----------------------------------------------


def rule_grain_duplicates(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    scan = scan_expr(sales_path)
    duplicate_key_groups, duplicate_rows_total, conflicting_key_groups = con.execute(
        f"""
        WITH grp AS (
            SELECT date, store_nbr, item_nbr, COUNT(*) AS n,
                   COUNT(DISTINCT unit_sales) AS distinct_unit_sales,
                   COUNT(DISTINCT COALESCE(CAST(onpromotion AS VARCHAR), 'NULL')) AS distinct_onpromotion
            FROM {scan}
            GROUP BY date, store_nbr, item_nbr
            HAVING COUNT(*) > 1
        )
        SELECT
            COUNT(*),
            COALESCE(SUM(n), 0),
            COALESCE(SUM(CASE WHEN distinct_unit_sales > 1 OR distinct_onpromotion > 1 THEN 1 ELSE 0 END), 0)
        FROM grp
        """
    ).fetchone()
    grain = checks.grain_uniqueness(con, sales_path, ("date", "store_nbr", "item_nbr"))

    metrics = {
        "total_rows": grain["total_rows"],
        "duplicate_key_groups": int(duplicate_key_groups),
        "duplicate_rows_total": int(duplicate_rows_total),
        "extra_rows_beyond_first_occurrence": grain["duplicate_rows"],
        "conflicting_key_groups": int(conflicting_key_groups),
    }

    if conflicting_key_groups > 0:
        # Not just repeated — the repeats disagree on a value. There is no
        # way to tell which row is correct without an external source, so
        # this is worse than a clean repeat.
        severity = CRITICAL
    elif duplicate_key_groups > 0:
        severity = HIGH
    else:
        severity = PASS

    return DQFinding(
        rule_id="grain_duplicates",
        category="grain",
        description="Rows sharing the same (date, store_nbr, item_nbr) key, which the "
        "sales table's declared grain requires to be unique.",
        metrics=metrics,
        severity=severity,
        consequence=(
            "Any join or aggregation at this grain double-counts these rows unless "
            "deduplicated. Where duplicates disagree on unit_sales or onpromotion, it "
            "is additionally ambiguous which value is correct."
            if duplicate_key_groups > 0
            else "None observed — grain is clean at this key."
        ),
        handling_decision=(
            "Deduplicate in staging (Phase 03), never in the raw layer: if a duplicate "
            "group agrees on all non-key values, keep one row; if it conflicts, keep the "
            "row with the highest `id` (treated as the later, superseding record) and log "
            "every conflict resolved, with its key and both values, to the staging load "
            "log so the decision is auditable."
        ),
    )


# --- R2: null/invalid keys ------------------------------------------------


def rule_null_keys(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    null_counts = checks.null_key_counts(con, sales_path, ("date", "store_nbr", "item_nbr"))
    total_null_key_rows = sum(null_counts.values())

    return DQFinding(
        rule_id="null_keys",
        category="keys",
        description="Rows with a NULL date, store_nbr, or item_nbr — any of which makes "
        "the row impossible to place at the declared grain.",
        metrics={"null_counts_by_column": null_counts, "total_null_key_rows": total_null_key_rows},
        severity=CRITICAL if total_null_key_rows > 0 else PASS,
        consequence=(
            "A null key cannot be placed in any hub x SKU x day cell; if coerced (e.g. "
            "to a sentinel value) it silently corrupts every downstream join and "
            "aggregation touching that key."
            if total_null_key_rows > 0
            else "None observed."
        ),
        handling_decision=(
            "Quarantine — do not load rows with a null key into the staging fact table. "
            "Write them to a named rejects file/table with the reason, for manual "
            "investigation, per CLAUDE.md §12's 'do not silently remove' rule: the row "
            "is kept somewhere inspectable, just not in the modeling path."
        ),
    )


# --- R3: orphan dimension references -------------------------------------


def rule_orphan_dimension_keys(
    con: duckdb.DuckDBPyConnection, sales_path: Path, stores_path: Path, items_path: Path
) -> DQFinding:
    refint = checks.referential_integrity(con, sales_path, stores_path, items_path)
    unknown_item = refint["sales_rows_with_unknown_item"]
    unknown_store = refint["sales_rows_with_unknown_store"]

    if unknown_item > 0 and unknown_store > 0:
        severity = HIGH
    elif unknown_item > 0:
        # Items churn far more than a store network does; still real, but a
        # narrower blast radius than an unknown store would be.
        severity = HIGH
    elif unknown_store > 0:
        severity = MEDIUM
    else:
        severity = PASS

    return DQFinding(
        rule_id="orphan_dimension_keys",
        category="dimensions",
        description="Sales rows whose store_nbr or item_nbr does not appear in the "
        "stores or items dimension table.",
        metrics=refint,
        severity=severity,
        consequence=(
            "These rows cannot be enriched with family/class/perishable (item) or "
            "city/state/type/cluster (store) — the JD's 'categories' and 'hubs' "
            "dimensions become unusable for exactly these rows, and an inner join "
            "against the dimension table would silently drop them rather than "
            "flagging them."
            if (unknown_item or unknown_store)
            else "None observed — every sales row's keys resolve to a known dimension row."
        ),
        handling_decision=(
            "Keep the fact row — never silently drop it — but flag it "
            "(`has_unknown_item` / `has_unknown_store`) in staging; exclude flagged rows "
            "from category- or hub-segmented analysis until resolved; route the finding "
            "to the Data Engineering stakeholder perspective (ADR 0001; dimension-table "
            "completeness is that perspective's ownership area, M-7c)."
        ),
    )


# --- R4: missing calendar dates / date gaps -------------------------------


def rule_missing_calendar_dates(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    coverage = checks.date_coverage(con, sales_path)
    missing = coverage["missing_dates_count"]
    expected = coverage["expected_calendar_days"] or 1
    share = missing / expected

    if missing == 0:
        severity = PASS
    elif share <= 0.02:
        severity = LOW
    elif share <= 0.10:
        severity = MEDIUM
    else:
        severity = HIGH

    return DQFinding(
        rule_id="missing_calendar_dates",
        category="dates",
        description="Calendar dates within the observed date range with zero sales rows "
        "across every store and item.",
        metrics={
            "missing_dates_count": missing,
            "expected_calendar_days": coverage["expected_calendar_days"],
            "missing_share": share,
            "missing_dates_sample": coverage["missing_dates_sample"],
        },
        severity=severity,
        consequence=(
            "A network-wide missing date is ambiguous between 'no data was delivered "
            "for that day' and 'the network was genuinely idle' — this directly affects "
            "the dense hub x SKU x day grid Phase 03 will build (Phase 00 assumption A3) "
            "and any day-of-week/seasonality feature that silently treats the gap as zero."
            if missing > 0
            else "None observed."
        ),
        handling_decision=(
            "Cross-check each missing date against known non-trading days documented for "
            "this dataset (e.g. no rows are reported for 25 December, per Phase 00 "
            "[VERIFY]); flag matches as `is_known_calendar_gap`. Any unexplained gap is "
            "logged to the Phase 11 discrepancy tracker rather than silently zero-filled."
        ),
    )


# --- R5: suspicious negative values (returns) -----------------------------


def rule_negative_values(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    validity = checks.value_validity(con, sales_path)
    share = validity["negative_unit_sales_share"]

    return DQFinding(
        rule_id="suspicious_negative_values",
        category="values",
        description="Rows with negative unit_sales — documented in public write-ups of "
        "this dataset as representing returns, not corrupted data.",
        metrics={
            "negative_unit_sales_count": validity["negative_unit_sales_count"],
            "negative_unit_sales_share": share,
        },
        severity=LOW if validity["negative_unit_sales_count"] > 0 else PASS,
        consequence=(
            "If naively summed as 'demand', returns understate true gross demand; any "
            "metric that means to represent demand (rather than net sales) must decide "
            "deliberately whether to net returns out, exclude them, or model them "
            "separately."
            if validity["negative_unit_sales_count"] > 0
            else "None observed."
        ),
        handling_decision=(
            "Retain — these are an expected, documented pattern, not a defect. Add an "
            "explicit `is_return` flag in staging. The choice of whether a given demand "
            "metric nets returns out is deferred to Phase 03/05 and must be stated "
            "explicitly wherever it's made, not assumed silently."
        ),
    )


# --- R6: suspicious extreme values ----------------------------------------


def rule_extreme_values(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    """A coarse, global IQR screen on positive unit_sales.

    Deliberately coarse: this is a Data Quality-level screen for "does this
    number look implausible at all", not the context-aware anomaly detection
    (promotions, holidays, per-series history) that Phase 04/09 will do. A
    flagged value might turn out to be a perfectly real bulk purchase.
    """
    scan = scan_expr(sales_path)
    q1, q3 = con.execute(
        f"""
        SELECT
            QUANTILE_CONT(unit_sales, 0.25),
            QUANTILE_CONT(unit_sales, 0.75)
        FROM {scan}
        WHERE unit_sales > 0
        """
    ).fetchone()
    if q1 is None or q3 is None:
        return DQFinding(
            rule_id="suspicious_extreme_values",
            category="values",
            description="Positive unit_sales values far beyond the bulk of the "
            "distribution's spread (an IQR fence), screened as a coarse DQ check.",
            metrics={"extreme_value_count": 0, "note": "no positive unit_sales rows found"},
            severity=PASS,
            consequence="None observed.",
            handling_decision="No action needed.",
        )

    iqr = q3 - q1
    upper_fence = q3 + EXTREME_VALUE_IQR_MULTIPLIER * iqr
    extreme_count, max_value = con.execute(
        f"SELECT COUNT(*), MAX(unit_sales) FROM {scan} WHERE unit_sales > {upper_fence}"
    ).fetchone()

    return DQFinding(
        rule_id="suspicious_extreme_values",
        category="values",
        description="Positive unit_sales values far beyond the bulk of the distribution's "
        "spread (Q3 + 3xIQR, a conventional far-outlier fence), screened as a coarse "
        "Data Quality check — not the context-aware anomaly analysis Phase 04/09 will do.",
        metrics={
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "upper_fence": upper_fence,
            "extreme_value_count": int(extreme_count or 0),
            "max_value_observed": max_value,
        },
        severity=MEDIUM if extreme_count and extreme_count > 0 else PASS,
        consequence=(
            "Could be a genuine bulk-purchase spike (real demand) or a data-entry error "
            "(e.g. a misplaced decimal) — magnitude alone cannot distinguish the two."
            if extreme_count and extreme_count > 0
            else "None observed at this fence."
        ),
        handling_decision=(
            "Flag, do not remove: carry an `is_extreme_value` flag into staging. Phase "
            "04 (demand analysis) and Phase 09 (RCA) investigate flagged points using "
            "business context — promotions, holidays, known events — before any "
            "modeling decision is made about them."
        ),
    )


# --- R7: onpromotion missing -----------------------------------------------


def rule_onpromotion_missing(con: duckdb.DuckDBPyConnection, sales_path: Path) -> DQFinding:
    validity = checks.value_validity(con, sales_path)
    share = validity["onpromotion_null_share"]

    if validity["onpromotion_null_count"] == 0:
        severity = PASS
    elif share > ONPROMOTION_NULL_HIGH_SEVERITY_THRESHOLD:
        severity = HIGH
    else:
        severity = MEDIUM

    return DQFinding(
        rule_id="onpromotion_missing",
        category="values",
        description="Rows with a NULL onpromotion flag: whether the item was on "
        "promotion that store-day is unknown, not known-false.",
        metrics={
            "onpromotion_null_count": validity["onpromotion_null_count"],
            "onpromotion_null_share": share,
            "high_severity_threshold": ONPROMOTION_NULL_HIGH_SEVERITY_THRESHOLD,
        },
        severity=severity,
        consequence=(
            "Directly degrades the JD's 'campaigns' dimension (M-1d): any promotion-"
            "uplift analysis must explicitly decide how to treat unknown-promotion rows "
            "(exclude vs. treat as not-promoted), and either choice biases the estimate "
            "somewhat."
            if validity["onpromotion_null_count"] > 0
            else "None observed."
        ),
        handling_decision=(
            "Keep NULL as a distinct third state — never silently coerce it to False. "
            "Whichever modeling choice is made about it in Phase 04's promotion-effect "
            "analysis must be stated explicitly there, not assumed here."
        ),
    )


# --- R8: missing JD-relevant dimension (pricing) --------------------------


def rule_missing_pricing_dimension(available_tables: list[str]) -> DQFinding:
    """A dataset-level structural gap, not a row-level defect.

    No column or table in this dataset carries item-level price at any grain
    (Phase 00 dataset comparison, ADR 0001 D2). This is a declarative check
    against the known Favorita table list, not a row-scan — there is no
    pricing table to scan.
    """
    pricing_present = any("price" in t.lower() for t in available_tables)
    return DQFinding(
        rule_id="missing_pricing_dimension",
        category="dimensions",
        description="Whether any acquired table carries an item-level pricing field.",
        metrics={"tables_checked": available_tables, "pricing_field_found": pricing_present},
        severity=PASS if pricing_present else INFO,
        consequence=(
            "None."
            if pricing_present
            else "JD dimension M-1e (pricing) cannot be analyzed from this dataset at all."
        ),
        handling_decision=(
            "N/A."
            if pricing_present
            else "Document as a dataset limitation (ADR 0001 D2; dataset card 'Known "
            "limitations'). Do not approximate with the oil-price macro indicator, and "
            "do not fabricate pricing data. No row-level remediation applies — this is "
            "structural, not repairable, within this dataset."
        ),
    )


def run_all_rules(
    con: duckdb.DuckDBPyConnection,
    sales_path: Path,
    stores_path: Path,
    items_path: Path,
    available_tables: list[str],
) -> list[DQFinding]:
    return [
        rule_grain_duplicates(con, sales_path),
        rule_null_keys(con, sales_path),
        rule_orphan_dimension_keys(con, sales_path, stores_path, items_path),
        rule_missing_calendar_dates(con, sales_path),
        rule_negative_values(con, sales_path),
        rule_extreme_values(con, sales_path),
        rule_onpromotion_missing(con, sales_path),
        rule_missing_pricing_dimension(available_tables),
    ]


def findings_to_dicts(findings: list[DQFinding]) -> list[dict[str, Any]]:
    return [asdict(f) for f in findings]


def _main() -> None:
    import json
    import logging

    from demandflow.config import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()

    sales_path = cfg.paths.parquet_dir / "train.parquet"
    stores_path = cfg.paths.parquet_dir / "stores.parquet"
    items_path = cfg.paths.parquet_dir / "items.parquet"
    for p in (sales_path, stores_path, items_path):
        if not p.exists():
            raise FileNotFoundError(f"Expected {p} to exist. Run demandflow.ingest.convert_to_parquet first.")

    available_tables = [p.stem for p in cfg.paths.parquet_dir.glob("*.parquet")]

    con = duckdb.connect()
    findings = run_all_rules(con, sales_path, stores_path, items_path, available_tables)
    con.close()

    out_path = cfg.paths.reports_dir / "phase02" / "dq_findings.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings_to_dicts(findings), indent=2), encoding="utf-8")

    for f in findings:
        print(f"[{f.severity:8s}] {f.rule_id}: {f.metrics}")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    _main()
