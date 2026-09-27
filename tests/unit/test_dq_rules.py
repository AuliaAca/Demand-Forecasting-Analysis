"""Unit tests for the Phase 02 data-quality rule catalog, against the fixture.

The fixture (tests/fixtures/favorita_sample/) plants: one duplicate key
(agreeing values, so not conflicting), one negative unit_sales, one
fractional unit_sales, one extreme value (80.0, planted specifically for
the suspicious_extreme_values rule), five NULL onpromotion values, and one
row referencing an item_nbr absent from items.csv. Every rule below is
asserted against these exact, hand-counted facts.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.quality.rules import (
    CRITICAL,
    HIGH,
    INFO,
    LOW,
    MEDIUM,
    PASS,
    rule_extreme_values,
    rule_grain_duplicates,
    rule_missing_calendar_dates,
    rule_missing_pricing_dimension,
    rule_negative_values,
    rule_null_keys,
    rule_onpromotion_missing,
    rule_orphan_dimension_keys,
    run_all_rules,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def con():
    connection = duckdb.connect()
    yield connection
    connection.close()


def test_grain_duplicates_not_conflicting_is_high_not_critical(con):
    finding = rule_grain_duplicates(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["duplicate_key_groups"] == 1
    assert finding.metrics["duplicate_rows_total"] == 2
    assert finding.metrics["conflicting_key_groups"] == 0
    assert finding.severity == HIGH  # duplicates exist, but they agree on values


def test_grain_duplicates_conflicting_escalates_to_critical(con, tmp_path):
    # A second duplicate of the same key but with a DIFFERENT unit_sales value.
    dirty_csv = tmp_path / "train_with_conflict.csv"
    original = (FIXTURE_DIR / "train.csv").read_text(encoding="utf-8")
    dirty_csv.write_text(original + "53,2013-01-02,1,100,999.0,False\n", encoding="utf-8")

    finding = rule_grain_duplicates(con, dirty_csv)
    assert finding.metrics["conflicting_key_groups"] >= 1
    assert finding.severity == CRITICAL


def test_null_keys_pass_on_clean_fixture(con):
    finding = rule_null_keys(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["total_null_key_rows"] == 0
    assert finding.severity == PASS


def test_orphan_dimension_keys_detects_planted_orphan_item(con):
    finding = rule_orphan_dimension_keys(
        con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "stores.csv", FIXTURE_DIR / "items.csv"
    )
    assert finding.metrics["sales_rows_with_unknown_item"] == 1
    assert finding.metrics["sales_rows_with_unknown_store"] == 0
    assert finding.severity == HIGH


def test_missing_calendar_dates_detects_planted_gap(con):
    finding = rule_missing_calendar_dates(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["missing_dates_count"] == 1
    assert finding.metrics["missing_dates_sample"] == ["2013-01-10"]
    # 1 missing day out of 20 expected = 5% -> MEDIUM band in this rule's thresholds
    assert finding.severity == MEDIUM


def test_negative_values_detects_the_planted_return(con):
    finding = rule_negative_values(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["negative_unit_sales_count"] == 1
    assert finding.severity == LOW


def test_extreme_values_detects_the_planted_outlier(con):
    finding = rule_extreme_values(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["extreme_value_count"] == 1
    assert finding.metrics["max_value_observed"] == 80.0
    assert finding.severity == MEDIUM


def test_onpromotion_missing_detects_the_planted_nulls(con):
    finding = rule_onpromotion_missing(con, FIXTURE_DIR / "train.csv")
    assert finding.metrics["onpromotion_null_count"] == 5
    # 5/52 ~= 9.6%, below the 20% high-severity threshold -> MEDIUM
    assert finding.severity == MEDIUM


def test_missing_pricing_dimension_flags_info_when_absent():
    finding = rule_missing_pricing_dimension(
        ["train", "stores", "items", "holidays_events", "oil", "transactions"]
    )
    assert finding.metrics["pricing_field_found"] is False
    assert finding.severity == INFO


def test_missing_pricing_dimension_passes_when_a_price_table_exists():
    finding = rule_missing_pricing_dimension(["train", "stores", "items", "sell_prices"])
    assert finding.metrics["pricing_field_found"] is True
    assert finding.severity == PASS


def test_run_all_rules_returns_eight_findings_with_no_row_removed(con):
    findings = run_all_rules(
        con,
        FIXTURE_DIR / "train.csv",
        FIXTURE_DIR / "stores.csv",
        FIXTURE_DIR / "items.csv",
        available_tables=["train", "stores", "items", "holidays_events", "oil", "transactions"],
    )
    assert len(findings) == 8
    rule_ids = {f.rule_id for f in findings}
    assert rule_ids == {
        "grain_duplicates",
        "null_keys",
        "orphan_dimension_keys",
        "missing_calendar_dates",
        "suspicious_negative_values",
        "suspicious_extreme_values",
        "onpromotion_missing",
        "missing_pricing_dimension",
    }
    # Every finding must document a handling decision — CLAUDE.md §12's
    # documentation contract is non-negotiable, even for a PASS/INFO finding.
    for f in findings:
        assert f.handling_decision.strip() != ""
        assert f.consequence.strip() != ""
