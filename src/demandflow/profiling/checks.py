"""Descriptive profiling checks for the Favorita dataset.

Scope note (phase discipline, CLAUDE.md §18): these functions *describe*
what is in the data — schema, grain, coverage, value ranges — for Phase 01's
"inspect schema/grain/size/time coverage" objective. They deliberately do
NOT assign severity, consequence, or a handling decision to what they find;
that rule/finding/severity/consequence/handling-decision documentation
format (CLAUDE.md §12) belongs to Phase 02 (Data Quality), which has not
started. Phase 01 only needs to know *what's there* well enough to write an
honest dataset card and decide the development scope.

Every function takes an explicit file path (Parquet or CSV) and a DuckDB
connection, and works identically against the tiny synthetic fixture in
tests/fixtures/favorita_sample/ and against the real, full-size files —
that's what tests/unit/test_checks.py verifies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


def scan_expr(path: Path) -> str:
    """A DuckDB table-producing expression for either a Parquet or CSV file."""
    posix = Path(path).as_posix()
    if posix.endswith(".parquet"):
        return f"read_parquet('{posix}')"
    return f"read_csv_auto('{posix}', SAMPLE_SIZE=-1)"


def schema_info(con: duckdb.DuckDBPyConnection, path: Path) -> list[dict[str, str]]:
    rows = con.execute(f"DESCRIBE SELECT * FROM {scan_expr(path)}").fetchall()
    return [{"column": r[0], "type": r[1]} for r in rows]


def row_count(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    (n,) = con.execute(f"SELECT COUNT(*) FROM {scan_expr(path)}").fetchone()
    return int(n)


def grain_uniqueness(
    con: duckdb.DuckDBPyConnection, sales_path: Path, key_columns: tuple[str, ...]
) -> dict[str, Any]:
    """Is (date, store_nbr, item_nbr) — or whatever key_columns is — unique?"""
    scan = scan_expr(sales_path)
    keys = ", ".join(key_columns)
    total, distinct = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT ({keys})) FROM {scan}"
    ).fetchone()
    return {
        "key_columns": list(key_columns),
        "total_rows": int(total),
        "distinct_key_rows": int(distinct),
        "duplicate_rows": int(total) - int(distinct),
        "is_unique": int(total) == int(distinct),
    }


def null_key_counts(
    con: duckdb.DuckDBPyConnection, path: Path, key_columns: tuple[str, ...]
) -> dict[str, int]:
    scan = scan_expr(path)
    result: dict[str, int] = {}
    for col in key_columns:
        (n,) = con.execute(f"SELECT COUNT(*) FROM {scan} WHERE {col} IS NULL").fetchone()
        result[col] = int(n)
    return result


def date_coverage(con: duckdb.DuckDBPyConnection, path: Path, date_column: str = "date") -> dict[str, Any]:
    scan = scan_expr(path)
    min_date, max_date, distinct_dates = con.execute(
        f"SELECT MIN({date_column}), MAX({date_column}), COUNT(DISTINCT {date_column}) FROM {scan}"
    ).fetchone()
    if min_date is None:
        return {
            "min_date": None,
            "max_date": None,
            "distinct_dates": 0,
            "expected_calendar_days": 0,
            "missing_dates_count": 0,
            "missing_dates_sample": [],
        }
    expected_days = (max_date - min_date).days + 1
    missing_rows = con.execute(
        f"""
        WITH calendar AS (
            SELECT CAST(UNNEST(generate_series(DATE '{min_date}', DATE '{max_date}', INTERVAL 1 DAY)) AS DATE) AS d
        ),
        present AS (
            SELECT DISTINCT CAST({date_column} AS DATE) AS d FROM {scan}
        )
        SELECT CAST(calendar.d AS DATE)
        FROM calendar
        LEFT JOIN present USING (d)
        WHERE present.d IS NULL
        ORDER BY calendar.d
        """
    ).fetchall()
    # Defensive formatting: keep only the date part even if a DuckDB version
    # or CSV type-inference quirk hands back a datetime-with-time value.
    missing_dates = [str(r[0])[:10] for r in missing_rows]
    return {
        "min_date": str(min_date),
        "max_date": str(max_date),
        "distinct_dates": int(distinct_dates),
        "expected_calendar_days": int(expected_days),
        "missing_dates_count": len(missing_dates),
        "missing_dates_sample": missing_dates[:20],
    }


def value_validity(con: duckdb.DuckDBPyConnection, sales_path: Path) -> dict[str, Any]:
    scan = scan_expr(sales_path)
    total = row_count(con, sales_path)
    negative_count, fractional_count = con.execute(
        f"""
        SELECT
            SUM(CASE WHEN unit_sales < 0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN unit_sales <> FLOOR(unit_sales) THEN 1 ELSE 0 END)
        FROM {scan}
        """
    ).fetchone()
    onpromo_null, onpromo_true, onpromo_false = con.execute(
        f"""
        SELECT
            SUM(CASE WHEN onpromotion IS NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN onpromotion = TRUE THEN 1 ELSE 0 END),
            SUM(CASE WHEN onpromotion = FALSE THEN 1 ELSE 0 END)
        FROM {scan}
        """
    ).fetchone()
    return {
        "total_rows": total,
        "negative_unit_sales_count": int(negative_count or 0),
        "negative_unit_sales_share": (negative_count or 0) / total if total else 0.0,
        "fractional_unit_sales_count": int(fractional_count or 0),
        "onpromotion_null_count": int(onpromo_null or 0),
        "onpromotion_null_share": (onpromo_null or 0) / total if total else 0.0,
        "onpromotion_true_count": int(onpromo_true or 0),
        "onpromotion_false_count": int(onpromo_false or 0),
    }


def referential_integrity(
    con: duckdb.DuckDBPyConnection,
    sales_path: Path,
    stores_path: Path,
    items_path: Path,
) -> dict[str, Any]:
    sales, stores, items = scan_expr(sales_path), scan_expr(stores_path), scan_expr(items_path)
    (orphan_stores,) = con.execute(
        f"""
        SELECT COUNT(*) FROM {sales} s
        WHERE NOT EXISTS (SELECT 1 FROM {stores} st WHERE st.store_nbr = s.store_nbr)
        """
    ).fetchone()
    (orphan_items,) = con.execute(
        f"""
        SELECT COUNT(*) FROM {sales} s
        WHERE NOT EXISTS (SELECT 1 FROM {items} it WHERE it.item_nbr = s.item_nbr)
        """
    ).fetchone()
    return {
        "sales_rows_with_unknown_store": int(orphan_stores),
        "sales_rows_with_unknown_item": int(orphan_items),
    }


def dimension_coverage(
    con: duckdb.DuckDBPyConnection,
    stores_path: Path,
    items_path: Path,
    holidays_path: Path,
) -> dict[str, Any]:
    stores, items, holidays = (
        scan_expr(stores_path),
        scan_expr(items_path),
        scan_expr(holidays_path),
    )
    n_stores, n_cities, n_states, n_types, n_clusters = con.execute(
        f"""
        SELECT COUNT(*), COUNT(DISTINCT city), COUNT(DISTINCT state),
               COUNT(DISTINCT type), COUNT(DISTINCT cluster)
        FROM {stores}
        """
    ).fetchone()
    n_items, n_families, n_classes, n_perishable = con.execute(
        f"""
        SELECT COUNT(*), COUNT(DISTINCT family), COUNT(DISTINCT class),
               SUM(CASE WHEN perishable = 1 THEN 1 ELSE 0 END)
        FROM {items}
        """
    ).fetchone()
    holiday_types = con.execute(
        f"SELECT type, COUNT(*) FROM {holidays} GROUP BY type ORDER BY 2 DESC"
    ).fetchall()
    holiday_locales = con.execute(
        f"SELECT locale, COUNT(*) FROM {holidays} GROUP BY locale ORDER BY 2 DESC"
    ).fetchall()
    return {
        "stores": {
            "count": int(n_stores),
            "distinct_cities": int(n_cities),
            "distinct_states": int(n_states),
            "distinct_types": int(n_types),
            "distinct_clusters": int(n_clusters),
        },
        "items": {
            "count": int(n_items),
            "distinct_families": int(n_families),
            "distinct_classes": int(n_classes),
            "perishable_count": int(n_perishable or 0),
            "non_perishable_count": int(n_items) - int(n_perishable or 0),
        },
        "holidays_events": {
            "by_type": {t: int(c) for t, c in holiday_types},
            "by_locale": {loc: int(c) for loc, c in holiday_locales},
        },
    }
