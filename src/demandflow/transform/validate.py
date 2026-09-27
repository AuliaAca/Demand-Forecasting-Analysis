"""Reconciliation checks run after the warehouse is built.

CLAUDE.md's engineering principles call for "clear data contracts/grain,
validation" -- these are structural invariants the layered SQL models must
satisfy. This is not a re-run of Phase 02's DQ rules (those already ran on
the raw layer, in demandflow.quality.rules); this module checks that the
*transformations themselves* (dedup, dense-fill, dimension joins) did what
they claim to do.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class ReconciliationCheck:
    name: str
    passed: bool
    detail: str


def run_reconciliation_checks(con: duckdb.DuckDBPyConnection) -> list[ReconciliationCheck]:
    checks: list[ReconciliationCheck] = []

    # 1. fct_sales_daily's declared grain is actually unique.
    total, distinct = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT (store_nbr, item_nbr, date)) FROM fct_sales_daily"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "fct_sales_daily_grain_unique",
            total == distinct,
            f"{total} rows, {distinct} distinct (store_nbr,item_nbr,date) keys",
        )
    )

    # 2. Every deduplicated staging row shows up as exactly one non-imputed
    #    row in the dense fact table -- dedup and dense-fill didn't lose or
    #    duplicate a real observation.
    staged, real_in_fact = con.execute(
        "SELECT (SELECT COUNT(*) FROM stg_sales), "
        "(SELECT COUNT(*) FROM fct_sales_daily WHERE NOT is_imputed_zero)"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "real_rows_reconcile_with_staging",
            staged == real_in_fact,
            f"stg_sales={staged}, fct_sales_daily non-imputed={real_in_fact}",
        )
    )

    # 3. dim_hub covers every store in the raw dimension table (stores are
    #    never scoped down, per ADR 0001 A1 / Section 2.1).
    raw_stores_n, dim_hub_n = con.execute(
        "SELECT (SELECT COUNT(*) FROM raw_stores), (SELECT COUNT(*) FROM dim_hub)"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "dim_hub_covers_all_stores",
            raw_stores_n == dim_hub_n,
            f"raw_stores={raw_stores_n}, dim_hub={dim_hub_n}",
        )
    )

    # 4. dim_sku covers the full item catalog (dev-scope filtering only
    #    applies to the sales fact table, not the dimension table).
    raw_items_n, dim_sku_n = con.execute(
        "SELECT (SELECT COUNT(*) FROM raw_items), (SELECT COUNT(*) FROM dim_sku)"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "dim_sku_covers_full_catalog",
            raw_items_n == dim_sku_n,
            f"raw_items={raw_items_n}, dim_sku={dim_sku_n}",
        )
    )

    # 5. No null keys survived into the fact table -- Phase 02 R2's
    #    quarantine decision, actually enforced, not just documented.
    (null_key_rows,) = con.execute(
        "SELECT COUNT(*) FROM fct_sales_daily "
        "WHERE store_nbr IS NULL OR item_nbr IS NULL OR date IS NULL"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "no_null_keys_in_fact_table", null_key_rows == 0, f"{null_key_rows} null-key rows"
        )
    )

    # 6. Every Phase 02 DQ rule produced exactly one row in fct_dq_result.
    (dq_row_count,) = con.execute("SELECT COUNT(*) FROM fct_dq_result").fetchone()
    checks.append(
        ReconciliationCheck(
            "fct_dq_result_has_all_rules",
            dq_row_count == 8,
            f"{dq_row_count} rows (expected 8)",
        )
    )

    # 7. The dev-scope filter never silently dropped an orphan-item row: an
    #    unrecognized item can't be "in scope", so it must be let through
    #    regardless (see 07_stg_sales.sql).
    orphan_in_stg, orphan_in_fact = con.execute(
        "SELECT (SELECT COUNT(*) FROM stg_sales WHERE has_unknown_item), "
        "(SELECT COUNT(*) FROM fct_sales_daily WHERE has_unknown_item)"
    ).fetchone()
    checks.append(
        ReconciliationCheck(
            "orphan_item_rows_not_silently_dropped",
            orphan_in_fact == orphan_in_stg,
            f"stg_sales has_unknown_item={orphan_in_stg}, fct_sales_daily={orphan_in_fact}",
        )
    )

    return checks
