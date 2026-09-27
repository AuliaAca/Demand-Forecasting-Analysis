"""Builds the Phase 03 DuckDB warehouse.

Registers raw views over Phase 01's Parquet files, runs the layered SQL
models under sql/ (staging -> intermediate -> marts), loads Phase 02's DQ
findings as a queryable mart (fct_dq_result), and runs the reconciliation
checks in demandflow.transform.validate.

fct_dq_result is loaded from Python, not a .sql file: its source is the
DQFinding dataclasses produced by demandflow.quality.rules.run_all_rules(),
which is naturally a Python object-construction step (each finding's
severity/consequence/handling text is authored in Python, not derived by a
SQL aggregation) that is then loaded into a table for queryability -- a
normal pattern, not a gap in the SQL layer.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.quality.rules import findings_to_dicts, run_all_rules
from demandflow.transform.sql_runner import register_raw_views, run_layer
from demandflow.transform.validate import ReconciliationCheck, run_reconciliation_checks

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SQL_DIR = REPO_ROOT / "sql"


def _load_fct_dq_result(
    con: duckdb.DuckDBPyConnection,
    sales_path: Path,
    stores_path: Path,
    items_path: Path,
    available_tables: list[str],
) -> None:
    findings = run_all_rules(con, sales_path, stores_path, items_path, available_tables)
    rows = findings_to_dicts(findings)

    con.execute(
        """
        CREATE OR REPLACE TABLE fct_dq_result (
            rule_id VARCHAR,
            category VARCHAR,
            description VARCHAR,
            severity VARCHAR,
            consequence VARCHAR,
            handling_decision VARCHAR,
            metrics_json VARCHAR,
            generated_at TIMESTAMP
        )
        """
    )
    now = datetime.now(timezone.utc)
    for r in rows:
        con.execute(
            "INSERT INTO fct_dq_result VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                r["rule_id"],
                r["category"],
                r["description"],
                r["severity"],
                r["consequence"],
                r["handling_decision"],
                json.dumps(r["metrics"]),
                now,
            ],
        )


def build_warehouse(
    cfg: ProjectConfig | None = None,
    db_path: Path | None = None,
    dev_scope_csv_path: Path | None = None,
) -> tuple[duckdb.DuckDBPyConnection, list[ReconciliationCheck]]:
    """Build (or rebuild) the warehouse and return the open connection plus
    the reconciliation-check results. The caller decides what to do with a
    failing check and is responsible for closing the connection.

    `dev_scope_csv_path` defaults to `cfg.paths.configs_dir / "dev_scope_items.csv"`
    (the real, frozen selection) but can be overridden -- tests pass a
    tmp_path location so a test run never writes into the repository's real
    configs/ directory.
    """
    cfg = cfg or load_config()
    db_path = db_path or (cfg.paths.data_dir / "warehouse" / "demandflow.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    dev_scope_csv_path = dev_scope_csv_path or (cfg.paths.configs_dir / "dev_scope_items.csv")

    if not dev_scope_csv_path.exists():
        raise FileNotFoundError(
            f"Expected {dev_scope_csv_path} to exist. Run demandflow.scope.select_dev_scope first."
        )

    con = duckdb.connect(str(db_path))
    registered = register_raw_views(con, cfg.paths.parquet_dir)
    logger.info("Registered raw views: %s", registered)

    substitutions = {"__DEV_SCOPE_ITEMS_CSV__": dev_scope_csv_path.as_posix()}

    staging_files = run_layer(con, SQL_DIR / "staging", substitutions)
    logger.info("Staging: %s", staging_files)
    intermediate_files = run_layer(con, SQL_DIR / "intermediate", substitutions)
    logger.info("Intermediate: %s", intermediate_files)
    marts_files = run_layer(con, SQL_DIR / "marts", substitutions)
    logger.info("Marts: %s", marts_files)

    available_tables = [p.stem for p in cfg.paths.parquet_dir.glob("*.parquet")]
    _load_fct_dq_result(
        con,
        cfg.paths.parquet_dir / "train.parquet",
        cfg.paths.parquet_dir / "stores.parquet",
        cfg.paths.parquet_dir / "items.parquet",
        available_tables,
    )

    checks = run_reconciliation_checks(con)
    for c in checks:
        level = logging.INFO if c.passed else logging.ERROR
        logger.log(level, "[%s] %s: %s", "PASS" if c.passed else "FAIL", c.name, c.detail)

    return con, checks


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    con, checks = build_warehouse()
    failed = [c for c in checks if not c.passed]
    con.close()
    if failed:
        raise SystemExit(f"{len(failed)} reconciliation check(s) failed: {[c.name for c in failed]}")
    print("All reconciliation checks passed.")


if __name__ == "__main__":
    _main()
