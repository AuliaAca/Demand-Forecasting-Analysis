"""Unit tests for demandflow.profiling.checks against the synthetic fixture.

tests/fixtures/favorita_sample/ is a small, hand-built, deliberately dirty
dataset (see its files) with known, hand-counted issues: one duplicate
(date, store_nbr, item_nbr) row, one negative unit_sales, one fractional
unit_sales, five NULL onpromotion values, one row referencing an item_nbr
not present in items.csv, and one entirely missing calendar date
(2013-01-10). These tests assert the exact expected counts, so a check
function that silently stops detecting one of these issues fails loudly.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.profiling import checks

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def con():
    connection = duckdb.connect()
    yield connection
    connection.close()


def test_row_count(con):
    assert checks.row_count(con, FIXTURE_DIR / "train.csv") == 51
    assert checks.row_count(con, FIXTURE_DIR / "stores.csv") == 5
    assert checks.row_count(con, FIXTURE_DIR / "items.csv") == 10


def test_grain_uniqueness_detects_the_planted_duplicate(con):
    result = checks.grain_uniqueness(
        con, FIXTURE_DIR / "train.csv", ("date", "store_nbr", "item_nbr")
    )
    assert result["total_rows"] == 51
    assert result["distinct_key_rows"] == 50
    assert result["duplicate_rows"] == 1
    assert result["is_unique"] is False


def test_null_key_counts_are_zero_on_this_fixture(con):
    result = checks.null_key_counts(
        con, FIXTURE_DIR / "train.csv", ("date", "store_nbr", "item_nbr")
    )
    assert result == {"date": 0, "store_nbr": 0, "item_nbr": 0}


def test_date_coverage_detects_the_planted_gap(con):
    result = checks.date_coverage(con, FIXTURE_DIR / "train.csv")
    assert result["min_date"] == "2013-01-01"
    assert result["max_date"] == "2013-01-20"
    assert result["expected_calendar_days"] == 20
    assert result["distinct_dates"] == 19
    assert result["missing_dates_count"] == 1
    assert result["missing_dates_sample"] == ["2013-01-10"]


def test_value_validity_detects_planted_negative_fractional_and_nulls(con):
    result = checks.value_validity(con, FIXTURE_DIR / "train.csv")
    assert result["total_rows"] == 51
    assert result["negative_unit_sales_count"] == 1
    assert result["fractional_unit_sales_count"] == 1
    assert result["onpromotion_null_count"] == 5
    assert result["onpromotion_true_count"] == 7
    assert result["onpromotion_false_count"] == 39
    assert result["onpromotion_null_count"] + result["onpromotion_true_count"] + result[
        "onpromotion_false_count"
    ] == result["total_rows"]


def test_referential_integrity_detects_the_planted_orphan_item(con):
    result = checks.referential_integrity(
        con,
        FIXTURE_DIR / "train.csv",
        FIXTURE_DIR / "stores.csv",
        FIXTURE_DIR / "items.csv",
    )
    assert result["sales_rows_with_unknown_store"] == 0
    assert result["sales_rows_with_unknown_item"] == 1


def test_dimension_coverage(con):
    result = checks.dimension_coverage(
        con,
        FIXTURE_DIR / "stores.csv",
        FIXTURE_DIR / "items.csv",
        FIXTURE_DIR / "holidays_events.csv",
    )
    assert result["stores"] == {
        "count": 5,
        "distinct_cities": 4,
        "distinct_states": 4,
        "distinct_types": 3,
        "distinct_clusters": 3,
    }
    assert result["items"]["count"] == 10
    assert result["items"]["distinct_families"] == 3
    assert result["items"]["perishable_count"] == 6
    assert result["items"]["non_perishable_count"] == 4
    assert result["holidays_events"]["by_type"] == {"Holiday": 2, "Bridge": 1}
    assert result["holidays_events"]["by_locale"] == {"National": 2, "Local": 1}


def test_schema_info_reports_declared_columns(con):
    schema = checks.schema_info(con, FIXTURE_DIR / "train.csv")
    columns = {row["column"] for row in schema}
    assert columns == {"id", "date", "store_nbr", "item_nbr", "unit_sales", "onpromotion"}
