"""Executes the layered SQL models (staging -> intermediate -> marts) against
a DuckDB connection.

[DECISION] Plain SQL files, one CREATE OR REPLACE TABLE/VIEW statement per
file, executed in filename order (numeric prefixes make the order explicit
on disk and are the actual execution mechanism via a sorted glob -- not a
separately maintained list that could drift from the files present). No
dbt (ADR 0001 D6) -- this is the "small Python runner" that decision
anticipated.

Path handling: SQL files reference other DuckDB tables/views by name only.
The one place a filesystem path is genuinely needed inside SQL text
(loading configs/dev_scope_items.csv) uses a `__TOKEN__`-style placeholder,
substituted here rather than hard-coded, so the same .sql file works
whether the data root is this sandbox's temp path or the project owner's
own D:\ (ADR 0001 Section 4.3).
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Raw Parquet files (Phase 01) registered as DuckDB views named raw_<table>.
RAW_TABLE_FILES = {
    "raw_train": "train.parquet",
    "raw_stores": "stores.parquet",
    "raw_items": "items.parquet",
    "raw_holidays_events": "holidays_events.parquet",
    "raw_oil": "oil.parquet",
    "raw_transactions": "transactions.parquet",
}


def register_raw_views(con: duckdb.DuckDBPyConnection, parquet_dir: Path) -> list[str]:
    """Create a DuckDB VIEW per available raw Parquet file (raw_<table>).

    Tables not present (e.g. test/sample_submission, never needed here) are
    skipped with a log message, matching Phase 01's tolerance.
    """
    registered = []
    for view_name, filename in RAW_TABLE_FILES.items():
        path = parquet_dir / filename
        if not path.exists():
            logger.info("Skipping %s: %s not found", view_name, path)
            continue
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{path.as_posix()}')"
        )
        registered.append(view_name)
    return registered


def run_sql_file(
    con: duckdb.DuckDBPyConnection, sql_path: Path, substitutions: dict[str, str] | None = None
) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    for token, value in (substitutions or {}).items():
        sql_text = sql_text.replace(token, value)
    con.execute(sql_text)


def run_layer(
    con: duckdb.DuckDBPyConnection, layer_dir: Path, substitutions: dict[str, str] | None = None
) -> list[str]:
    """Run every *.sql file in layer_dir, in filename (numeric-prefix) order."""
    executed = []
    for sql_file in sorted(layer_dir.glob("*.sql")):
        logger.info("Running %s", sql_file.name)
        run_sql_file(con, sql_file, substitutions)
        executed.append(sql_file.name)
    return executed
