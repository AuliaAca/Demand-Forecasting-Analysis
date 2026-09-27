"""Convert the raw Favorita CSVs to Parquet, without changing any values.

Uses DuckDB rather than pandas.read_csv() for the large files. DuckDB reads
CSV and writes Parquet out-of-core (it does not need the file to fit in
RAM), which is what makes the one-time full-file ingestion step workable on
modest hardware — see docs/decisions/0001-phase00-decisions-and-scope.md §4.

[DECISION] Column types below are asserted explicitly (not inferred) so a
schema surprise in the real file fails loudly here rather than silently
propagating downstream. Types come from the public documentation reviewed
in Phase 00 [VERIFY] — the first real run against the actual files is what
confirms or corrects them (see docs/phase_reports/phase01.md).
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config

logger = logging.getLogger(__name__)

# [VERIFY] Column definitions per Kaggle's public data description for this
# competition, reviewed during Phase 00. Confirmed or corrected on first real
# run — see the "columns" field DuckDB reports if a table's actual header
# does not match these names.
TABLE_SCHEMAS: dict[str, dict[str, str]] = {
    "train": {
        "id": "BIGINT",
        "date": "DATE",
        "store_nbr": "INTEGER",
        "item_nbr": "BIGINT",
        "unit_sales": "DOUBLE",
        "onpromotion": "BOOLEAN",
    },
    "test": {
        "id": "BIGINT",
        "date": "DATE",
        "store_nbr": "INTEGER",
        "item_nbr": "BIGINT",
        "onpromotion": "BOOLEAN",
    },
    "stores": {
        "store_nbr": "INTEGER",
        "city": "VARCHAR",
        "state": "VARCHAR",
        "type": "VARCHAR",
        "cluster": "INTEGER",
    },
    "items": {
        "item_nbr": "BIGINT",
        "family": "VARCHAR",
        "class": "INTEGER",
        "perishable": "INTEGER",
    },
    "holidays_events": {
        "date": "DATE",
        "type": "VARCHAR",
        "locale": "VARCHAR",
        "locale_name": "VARCHAR",
        "description": "VARCHAR",
        "transferred": "BOOLEAN",
    },
    "oil": {
        "date": "DATE",
        "dcoilwtico": "DOUBLE",
    },
    "transactions": {
        "date": "DATE",
        "store_nbr": "INTEGER",
        "transactions": "INTEGER",
    },
}


def _duckdb_types_clause(columns: dict[str, str]) -> str:
    pairs = ", ".join(f"'{name}': '{dtype}'" for name, dtype in columns.items())
    return "{" + pairs + "}"


def convert_table(
    con: duckdb.DuckDBPyConnection, csv_path: Path, parquet_path: Path, columns: dict[str, str]
) -> int:
    """Convert one CSV to one Parquet file with an explicit, asserted schema.

    Returns the row count written. Raises if the CSV's actual columns don't
    match `columns` (fail loudly rather than silently coercing/dropping).
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    types_clause = _duckdb_types_clause(columns)
    col_names = list(columns.keys())

    actual_cols = [
        row[0]
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_csv_auto('{csv_path.as_posix()}', SAMPLE_SIZE=-1)"
        ).fetchall()
    ]
    missing = set(col_names) - set(actual_cols)
    if missing:
        raise ValueError(
            f"{csv_path.name}: expected columns {sorted(missing)} not found in the file. "
            f"Actual columns: {actual_cols}. The public schema assumed in "
            "TABLE_SCHEMAS may not match this file — update it after inspecting "
            "the real header."
        )

    select_cols = ", ".join(col_names)
    con.execute(
        f"""
        COPY (
            SELECT {select_cols}
            FROM read_csv(
                '{csv_path.as_posix()}',
                columns = {types_clause},
                header = true
            )
        ) TO '{parquet_path.as_posix()}' (FORMAT PARQUET)
        """
    )
    (row_count,) = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')"
    ).fetchone()
    return int(row_count)


def convert_all(config: ProjectConfig | None = None) -> dict[str, int]:
    """Convert every table listed in TABLE_SCHEMAS that has a raw CSV present.

    Returns {table_name: row_count}. Tables whose CSV isn't present (e.g.
    test.csv/sample_submission.csv, which aren't needed for Phase 01
    profiling) are skipped with a log message, not an error.
    """
    cfg = config or load_config()
    results: dict[str, int] = {}
    with duckdb.connect() as con:
        for table_name, columns in TABLE_SCHEMAS.items():
            csv_path = cfg.paths.raw_dir / f"{table_name}.csv"
            if not csv_path.exists():
                logger.info("Skipping %s: %s not found", table_name, csv_path)
                continue
            parquet_path = cfg.paths.parquet_dir / f"{table_name}.parquet"
            logger.info("Converting %s -> %s", csv_path.name, parquet_path)
            results[table_name] = convert_table(con, csv_path, parquet_path, columns)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    counts = convert_all()
    for name, n in counts.items():
        print(f"{name}: {n:,} rows")
