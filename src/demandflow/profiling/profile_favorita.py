"""Run the full Phase 01 profiling pass and write reports/phase01/profile_summary.json.

This is the "inspect schema/grain/size/time coverage" half of Phase 01's
objective. It is safe to run against either the real converted Parquet files
or the raw CSVs directly (checks.py handles both), so it can also be run
straight after acquire_favorita.py without waiting on the Parquet conversion.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.profiling import checks

logger = logging.getLogger(__name__)


@dataclass
class ProfileReport:
    profiled_at_utc: str
    source_dir: str
    tables_present: list[str]
    row_counts: dict[str, int]
    schemas: dict[str, list[dict[str, str]]]
    sales_grain: dict[str, Any]
    sales_null_keys: dict[str, int]
    sales_date_coverage: dict[str, Any]
    sales_value_validity: dict[str, Any]
    referential_integrity: dict[str, Any]
    dimension_coverage: dict[str, Any]


def _find_table(data_dir: Path, name: str) -> Path | None:
    parquet_path = data_dir / f"{name}.parquet"
    if parquet_path.exists():
        return parquet_path
    csv_path = data_dir / f"{name}.csv"
    if csv_path.exists():
        return csv_path
    return None


def profile(config: ProjectConfig | None = None, prefer_parquet: bool = True) -> ProfileReport:
    cfg = config or load_config()
    source_dir = cfg.paths.parquet_dir if prefer_parquet and cfg.paths.parquet_dir.exists() else cfg.paths.raw_dir

    table_names = ["train", "stores", "items", "holidays_events", "oil", "transactions"]
    paths: dict[str, Path] = {}
    for name in table_names:
        found = _find_table(source_dir, name)
        if found is None:
            found = _find_table(cfg.paths.raw_dir, name)
        if found is not None:
            paths[name] = found

    missing = [n for n in table_names if n not in paths]
    if missing:
        logger.warning("Tables not found and skipped: %s", missing)

    with duckdb.connect() as con:
        row_counts = {name: checks.row_count(con, p) for name, p in paths.items()}
        schemas = {name: checks.schema_info(con, p) for name, p in paths.items()}

        sales_grain: dict[str, Any] = {}
        sales_null_keys: dict[str, int] = {}
        sales_date_coverage: dict[str, Any] = {}
        sales_value_validity: dict[str, Any] = {}
        referential_integrity: dict[str, Any] = {}
        if "train" in paths:
            sales_grain = checks.grain_uniqueness(con, paths["train"], ("date", "store_nbr", "item_nbr"))
            sales_null_keys = checks.null_key_counts(con, paths["train"], ("date", "store_nbr", "item_nbr"))
            sales_date_coverage = checks.date_coverage(con, paths["train"])
            sales_value_validity = checks.value_validity(con, paths["train"])
            if "stores" in paths and "items" in paths:
                referential_integrity = checks.referential_integrity(
                    con, paths["train"], paths["stores"], paths["items"]
                )

        dimension_coverage: dict[str, Any] = {}
        if "stores" in paths and "items" in paths and "holidays_events" in paths:
            dimension_coverage = checks.dimension_coverage(
                con, paths["stores"], paths["items"], paths["holidays_events"]
            )

    return ProfileReport(
        profiled_at_utc=datetime.now(timezone.utc).isoformat(),
        source_dir=str(source_dir),
        tables_present=sorted(paths.keys()),
        row_counts=row_counts,
        schemas=schemas,
        sales_grain=sales_grain,
        sales_null_keys=sales_null_keys,
        sales_date_coverage=sales_date_coverage,
        sales_value_validity=sales_value_validity,
        referential_integrity=referential_integrity,
        dimension_coverage=dimension_coverage,
    )


def write_report(report: ProfileReport, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    report = profile(cfg)
    out = write_report(report, cfg.paths.reports_dir / "phase01" / "profile_summary.json")
    print(f"Wrote profiling report to {out}")
