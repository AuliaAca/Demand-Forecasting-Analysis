"""Phase 13 -- offline validation for the BigQuery SQL port (sql/bigquery/).

This sandbox has no real GCP project or billing account (the same kind of
real-access gap every phase has disclosed since Phase 01's "no Kaggle
credentials"), so nothing under sql/bigquery/ has ever been run against a
live BigQuery instance. What CAN be validated without one: whether each
file is syntactically valid BigQuery Standard SQL at all. `sqlglot` is a
real, offline, dialect-aware SQL parser -- parsing every file with
`dialect="bigquery"` is genuine (if partial) evidence of correctness, well
beyond "it looks right," even though it cannot catch a query that parses
but fails at execution time (a nonexistent function, a real permissions or
quota error, a semantic type mismatch BigQuery's own analyzer would
reject).

`render_sql()` mirrors demandflow.transform.sql_runner's own
`__TOKEN__`-substitution approach (same pattern, different tokens: a
BigQuery table is `` `project.dataset.table` ``, not a bare DuckDB table
name) -- reused deliberately for consistency between the two SQL runners,
not reinvented.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

SQL_ROOT = Path(__file__).resolve().parents[3] / "sql" / "bigquery"
LAYERS = ["staging", "intermediate", "marts"]


def render_sql(sql_text: str, project: str, dataset: str) -> str:
    return sql_text.replace("__PROJECT__", project).replace("__DATASET__", dataset)


def list_sql_files(sql_root: Path = SQL_ROOT) -> list[Path]:
    """Every *.sql file across the three layers, in the same
    layer-then-filename order demandflow.transform.sql_runner.run_layer()
    would execute them (staging, then intermediate, then marts; numeric
    filename prefixes within each)."""
    files = []
    for layer in LAYERS:
        files.extend(sorted((sql_root / layer).glob("*.sql")))
    return files


@dataclass(frozen=True)
class SqlFileCheck:
    path: str
    layer: str
    parses_ok: bool
    error: str | None
    table_name: str | None
    is_partitioned: bool
    is_clustered: bool
    partition_column: str | None
    cluster_columns: list[str]


def _table_name(create_expr: exp.Create) -> str | None:
    table = create_expr.this
    if isinstance(table, exp.Table):
        return table.name
    return None


def _partition_info(create_expr: exp.Create) -> tuple[bool, str | None]:
    properties = create_expr.args.get("properties")
    if properties is None:
        return False, None
    for prop in properties.expressions:
        if isinstance(prop, exp.PartitionedByProperty):
            col = prop.this
            return True, (col.name if hasattr(col, "name") else str(col))
    return False, None


def _cluster_info(create_expr: exp.Create) -> tuple[bool, list[str]]:
    properties = create_expr.args.get("properties")
    if properties is None:
        return False, []
    for prop in properties.expressions:
        if isinstance(prop, exp.ClusterProperty):
            cols = [c.name for c in prop.expressions]
            return True, cols
    return False, []


def check_sql_file(path: Path, project: str = "demandflow-validation", dataset: str = "demandflow") -> SqlFileCheck:
    layer = path.parent.name
    rendered = render_sql(path.read_text(encoding="utf-8"), project, dataset)
    try:
        parsed = sqlglot.parse_one(rendered, dialect="bigquery")
    except Exception as e:  # noqa: BLE001 -- reported in the result, not raised
        return SqlFileCheck(
            path=str(path), layer=layer, parses_ok=False, error=str(e),
            table_name=None, is_partitioned=False, is_clustered=False,
            partition_column=None, cluster_columns=[],
        )

    table_name = _table_name(parsed) if isinstance(parsed, exp.Create) else None
    is_partitioned, partition_column = (
        _partition_info(parsed) if isinstance(parsed, exp.Create) else (False, None)
    )
    is_clustered, cluster_columns = (
        _cluster_info(parsed) if isinstance(parsed, exp.Create) else (False, [])
    )
    return SqlFileCheck(
        path=str(path), layer=layer, parses_ok=True, error=None,
        table_name=table_name, is_partitioned=is_partitioned, is_clustered=is_clustered,
        partition_column=partition_column, cluster_columns=cluster_columns,
    )


def validate_all(sql_root: Path = SQL_ROOT, **kwargs: Any) -> list[SqlFileCheck]:
    return [check_sql_file(f, **kwargs) for f in list_sql_files(sql_root)]


def _main() -> None:
    results = validate_all()
    failed = [r for r in results if not r.parses_ok]
    for r in results:
        status = "OK  " if r.parses_ok else "FAIL"
        extra = ""
        if r.is_partitioned or r.is_clustered:
            extra = f" (partition={r.partition_column}, cluster={r.cluster_columns})"
        print(f"[{status}] {r.path}{extra}")
        if r.error:
            print(f"        {r.error}")
    print(f"\n{len(results) - len(failed)}/{len(results)} files parsed as valid BigQuery SQL")
    if failed:
        raise SystemExit(f"{len(failed)} file(s) failed to parse")


if __name__ == "__main__":
    _main()
