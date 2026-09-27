"""Tests for the Phase 13 BigQuery SQL port (sql/bigquery/).

This sandbox has no live BigQuery project, so these tests validate what
CAN be checked offline: every file parses as syntactically valid BigQuery
SQL (sqlglot), the partition/cluster design lands on exactly the three
tables it should, and the specific dialect gotchas this phase's review
package documents (day-of-week numbering, DATE_TRUNC argument order,
DOW vs. DAYOFWEEK, TIMESTAMP_TRUNC vs. DATE_TRUNC) are locked in as
regression tests -- including against sqlglot's own naive DuckDB ->
BigQuery auto-transpiler, which was found to emit genuinely invalid
BigQuery (EXTRACT(DOW ...), TIMESTAMP_TRUNC on a DATE column) for exactly
the files this phase's hand port fixed by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlglot

from demandflow.bigquery.validate_sql import SQL_ROOT, check_sql_file, list_sql_files, render_sql, validate_all

DUCKDB_SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"


def _code_only(sql_text: str) -> str:
    """Strips `--` line comments before a pattern check -- this file's own
    explanatory comments deliberately name the DuckDB-only constructs they
    warn against (e.g. "not EXTRACT(WEEK FROM date)"), which would
    otherwise false-positive a naive substring/regex check against the
    comment text itself rather than the actual SQL."""
    return "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )

PARTITIONED_AND_CLUSTERED_TABLES = {"stg_sales", "int_sales_daily_dense", "fct_sales_daily"}


def test_sql_root_has_the_expected_14_files():
    files = list_sql_files()
    assert len(files) == 14
    assert {f.name for f in files} == {
        "01_stg_dev_scope_items.sql", "02_stg_stores.sql", "03_stg_items.sql",
        "04_stg_holidays_events.sql", "05_stg_oil.sql", "06_stg_transactions.sql",
        "07_stg_sales.sql", "08_stg_sales_rejected_null_keys.sql",
        "01_int_calendar_by_store.sql", "02_int_sales_daily_dense.sql",
        "01_dim_hub.sql", "02_dim_sku.sql", "03_dim_date.sql", "04_fct_sales_daily.sql",
    }


def test_every_file_parses_as_valid_bigquery_sql():
    results = validate_all()
    failures = [r for r in results if not r.parses_ok]
    assert not failures, f"{len(failures)} file(s) failed to parse: {[(r.path, r.error) for r in failures]}"


@pytest.mark.parametrize("sql_file", list_sql_files(), ids=lambda p: p.name)
def test_each_file_individually_parses(sql_file):
    result = check_sql_file(sql_file)
    assert result.parses_ok, result.error


def test_only_the_three_high_volume_tables_are_partitioned_and_clustered():
    results = validate_all()
    partitioned = {r.table_name for r in results if r.is_partitioned}
    clustered = {r.table_name for r in results if r.is_clustered}
    assert partitioned == PARTITIONED_AND_CLUSTERED_TABLES
    assert clustered == PARTITIONED_AND_CLUSTERED_TABLES


def test_partitioned_tables_partition_by_date_and_cluster_by_store_and_item():
    results = validate_all()
    for r in results:
        if r.table_name in PARTITIONED_AND_CLUSTERED_TABLES:
            assert r.partition_column == "date"
            assert r.cluster_columns == ["store_nbr", "item_nbr"]


def test_dimension_tables_are_not_partitioned_or_clustered():
    results = validate_all()
    dimension_tables = {"dim_hub", "dim_sku", "dim_date"}
    for r in results:
        if r.table_name in dimension_tables:
            assert not r.is_partitioned
            assert not r.is_clustered


# --- render_sql (token substitution) ----------------------------------------


def test_render_sql_substitutes_both_tokens():
    rendered = render_sql("SELECT * FROM `__PROJECT__.__DATASET__.t`", "myproj", "mydataset")
    assert rendered == "SELECT * FROM `myproj.mydataset.t`"
    assert "__PROJECT__" not in rendered
    assert "__DATASET__" not in rendered


def test_no_file_has_an_unsubstituted_token_leak_beyond_the_two_known_ones():
    # every occurrence of a double-underscore token must be one of the two
    # this module knows how to substitute -- catches a typo'd token that
    # would otherwise silently survive into "rendered" SQL.
    for f in list_sql_files():
        rendered = render_sql(f.read_text(encoding="utf-8"), "p", "d")
        assert "__" not in rendered, f"{f} has an unsubstituted token after rendering"


# --- dialect-correctness regressions ----------------------------------------


def test_no_file_uses_duckdbs_dow_extract_field():
    # BigQuery has no DOW date part (EXTRACT(DOW FROM ...) is a DuckDB-ism);
    # sqlglot's own naive DuckDB->BigQuery transpiler was found to emit it
    # verbatim, which is not valid BigQuery. DAYOFWEEK is the real field.
    for f in list_sql_files():
        code = _code_only(f.read_text(encoding="utf-8"))
        assert "EXTRACT(dow" not in code.lower(), f"{f} uses DuckDB's dow extract field"


def test_day_of_week_is_normalized_to_sunday_zero():
    # BigQuery's DAYOFWEEK is 1=Sunday..7=Saturday; DuckDB's dow is
    # 0=Sunday..6=Saturday. Every EXTRACT(DAYOFWEEK ...) in this port must
    # be followed by "- 1" to preserve DuckDB's convention.
    for f in list_sql_files():
        code = _code_only(f.read_text(encoding="utf-8"))
        if "DAYOFWEEK" in code:
            assert "EXTRACT(DAYOFWEEK FROM" in code
            # every DAYOFWEEK extraction in this file is immediately
            # followed by the normalization subtraction
            for line in code.splitlines():
                if "EXTRACT(DAYOFWEEK FROM" in line:
                    assert "- 1" in line, f"{f}: {line!r} does not normalize DAYOFWEEK to Sunday=0"


def test_no_file_uses_timestamp_trunc_on_a_date_column():
    # DATE_TRUNC(date_expr, part) is BigQuery's DATE-typed truncation;
    # TIMESTAMP_TRUNC expects a TIMESTAMP and is a type error against this
    # project's DATE columns. sqlglot's naive transpiler was found to emit
    # TIMESTAMP_TRUNC here -- this pins the correct function.
    for f in list_sql_files():
        code = _code_only(f.read_text(encoding="utf-8"))
        assert "TIMESTAMP_TRUNC" not in code, f"{f} uses TIMESTAMP_TRUNC on what should be a DATE column"


def test_iso_week_uses_isoweek_not_plain_week():
    dim_date = _code_only((SQL_ROOT / "marts" / "03_dim_date.sql").read_text(encoding="utf-8"))
    assert "EXTRACT(ISOWEEK FROM date)" in dim_date
    assert "EXTRACT(WEEK FROM date)" not in dim_date


def test_stg_sales_avoids_count_distinct_inside_a_window_function():
    # BigQuery's analytic functions do not reliably support DISTINCT the
    # way DuckDB's COUNT(DISTINCT x) OVER (...) does; this file must use a
    # GROUP BY + JOIN instead.
    import re

    stg_sales = _code_only((SQL_ROOT / "staging" / "07_stg_sales.sql").read_text(encoding="utf-8"))
    assert "COUNT(DISTINCT" in stg_sales  # the ordinary GROUP BY aggregate form is still used
    assert not re.search(r"COUNT\(DISTINCT[^)]*\)\s*OVER\s*\(", stg_sales)  # never inside a window


# --- cross-check against sqlglot's own DuckDB -> BigQuery transpiler -------


@pytest.mark.parametrize(
    "duckdb_path,bigquery_path",
    [
        ("staging/02_stg_stores.sql", "staging/02_stg_stores.sql"),
        ("staging/03_stg_items.sql", "staging/03_stg_items.sql"),
        ("staging/04_stg_holidays_events.sql", "staging/04_stg_holidays_events.sql"),
        ("staging/05_stg_oil.sql", "staging/05_stg_oil.sql"),
        ("staging/06_stg_transactions.sql", "staging/06_stg_transactions.sql"),
        ("marts/01_dim_hub.sql", "marts/01_dim_hub.sql"),
        ("marts/02_dim_sku.sql", "marts/02_dim_sku.sql"),
    ],
)
def test_simple_passthroughs_match_sqlglots_automated_transpile(duckdb_path, bigquery_path):
    # For files with no dialect-specific pitfalls, an automated DuckDB ->
    # BigQuery transpile of the ORIGINAL DuckDB source should select the
    # same columns from the same table as this phase's hand port -- a
    # structural cross-check, not just "it also parses."
    duckdb_sql = (DUCKDB_SQL_ROOT / duckdb_path).read_text(encoding="utf-8")
    auto_transpiled = sqlglot.parse_one(
        sqlglot.transpile(duckdb_sql, read="duckdb", write="bigquery")[0], dialect="bigquery"
    )
    hand_ported = sqlglot.parse_one(
        render_sql((SQL_ROOT / bigquery_path).read_text(encoding="utf-8"), "p", "d"), dialect="bigquery"
    )
    auto_select = auto_transpiled.find(sqlglot.exp.Select)
    hand_select = hand_ported.find(sqlglot.exp.Select)
    assert [e.sql() for e in auto_select.expressions] == [e.sql() for e in hand_select.expressions]
    assert auto_transpiled.this.name == hand_ported.this.name  # same target table name


def test_sqlglots_naive_transpile_of_the_calendar_file_is_confirmed_wrong():
    # Documents (as a passing, locked-in test) exactly why this phase's
    # calendar/date-dimension files were hand-verified rather than
    # generated: the naive transpile of the ORIGINAL DuckDB file emits
    # EXTRACT(DOW ...) and TIMESTAMP_TRUNC on a DATE column, neither of
    # which is valid, semantically-correct BigQuery -- exactly the two
    # things this phase's hand port fixed.
    duckdb_sql = (DUCKDB_SQL_ROOT / "intermediate" / "01_int_calendar_by_store.sql").read_text(encoding="utf-8")
    auto_transpiled = sqlglot.transpile(duckdb_sql, read="duckdb", write="bigquery")[0]
    assert "EXTRACT(DOW" in auto_transpiled
    assert "TIMESTAMP_TRUNC" in auto_transpiled


# --- the raw-load shell script ----------------------------------------------


def test_bigquery_load_raw_script_has_valid_bash_syntax():
    # `bash -n` is a real, offline, execution-free syntax check -- it is
    # what actually caught a genuine bug during this phase's own
    # development: an apostrophe inside a ${VAR:?message} parameter
    # expansion breaks bash's parser even though the whole expression is
    # wrapped in double quotes (a real, if obscure, bash gotcha -- not a
    # cosmetic issue). This test locks that fix in.
    import subprocess

    script = Path(__file__).resolve().parents[2] / "scripts" / "bigquery_load_raw.sh"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
