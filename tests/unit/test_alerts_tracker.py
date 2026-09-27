"""Unit tests for Phase 11's discrepancy tracker (demandflow.alerts.tracker)."""

import duckdb
import pytest

from demandflow.alerts.tracker import (
    calendar_gap_tracker_items,
    discrepancy_rca_tracker_items,
    ensure_tracker_table,
    load_tracker_items,
    upsert_tracker_items,
)


@pytest.fixture
def con():
    c = duckdb.connect()
    ensure_tracker_table(c)
    yield c
    c.close()


# --- calendar_gap_tracker_items ----------------------------------------------


def _dq_finding(rule_id, metrics):
    return {"rule_id": rule_id, "metrics": metrics}


def test_calendar_gap_tracker_items_empty_when_no_gaps():
    findings = [_dq_finding("missing_calendar_dates", {"missing_dates_count": 0, "missing_dates_sample": []})]
    assert calendar_gap_tracker_items(findings) == []


def test_calendar_gap_tracker_items_empty_when_rule_missing():
    assert calendar_gap_tracker_items([]) == []


def test_calendar_gap_tracker_items_flags_unknown_gap_as_open_warning():
    findings = [_dq_finding("missing_calendar_dates", {"missing_dates_count": 1, "missing_dates_sample": ["2013-01-10"]})]
    items = calendar_gap_tracker_items(findings)
    assert len(items) == 1
    assert items[0]["status"] == "open"
    assert items[0]["severity"] == "warning"
    assert items[0]["evidence"]["matches_known_non_trading_day"] is False


def test_calendar_gap_tracker_items_resolves_known_non_trading_day():
    findings = [_dq_finding("missing_calendar_dates", {"missing_dates_count": 1, "missing_dates_sample": ["2013-12-25"]})]
    items = calendar_gap_tracker_items(findings)
    assert items[0]["status"] == "resolved_known_non_trading_day"
    assert items[0]["severity"] == "info"


# --- discrepancy_rca_tracker_items ------------------------------------------


def _rca_record(dimension, segment, cause_unknown=True):
    statement = (
        "cause unknown from available evidence, requires further investigation"
        if cause_unknown else "associated with extreme values"
    )
    return {
        "dimension": dimension, "segment": segment,
        "trigger_statement": f"trigger for {dimension}={segment}",
        "statement": statement,
    }


def test_discrepancy_rca_tracker_items_only_includes_cause_unknown():
    rca_summary = {"forecast_discrepancy_rca": [
        _rca_record("holiday", "non_holiday", cause_unknown=True),
        _rca_record("item_family", "DAIRY", cause_unknown=False),
    ]}
    items = discrepancy_rca_tracker_items(rca_summary)
    assert len(items) == 1
    assert items[0]["natural_key"] == "forecast_discrepancy:holiday:non_holiday"


def test_discrepancy_rca_tracker_items_deduplicates_same_segment():
    rca_summary = {"forecast_discrepancy_rca": [
        _rca_record("payday", "payday", cause_unknown=True),
        _rca_record("payday", "payday", cause_unknown=True),
    ]}
    items = discrepancy_rca_tracker_items(rca_summary)
    assert len(items) == 1


def test_discrepancy_rca_tracker_items_empty_with_no_findings():
    assert discrepancy_rca_tracker_items({"forecast_discrepancy_rca": []}) == []


# --- upsert_tracker_items / load_tracker_items (DB-facing) ------------------


def _item(key, status="open"):
    return {
        "natural_key": key, "category": "calendar_gap", "severity": "warning", "status": status,
        "description": f"desc for {key}", "evidence": {"k": "v"},
    }


def test_upsert_tracker_items_inserts_new_items(con):
    result = upsert_tracker_items(con, [_item("k1")], run_timestamp="t1")
    assert result == {"inserted": 1, "updated": 0}
    items = load_tracker_items(con)
    assert len(items) == 1
    assert items[0]["times_seen"] == 1
    assert items[0]["first_seen_at"] == "t1"


def test_upsert_tracker_items_updates_existing_item_instead_of_duplicating(con):
    upsert_tracker_items(con, [_item("k1")], run_timestamp="t1")
    result = upsert_tracker_items(con, [_item("k1")], run_timestamp="t2")
    assert result == {"inserted": 0, "updated": 1}
    items = load_tracker_items(con)
    assert len(items) == 1  # no duplicate row
    assert items[0]["times_seen"] == 2
    assert items[0]["first_seen_at"] == "t1"  # unchanged
    assert items[0]["last_seen_at"] == "t2"


def test_load_tracker_items_open_only_excludes_resolved(con):
    upsert_tracker_items(con, [_item("k1", status="open"), _item("k2", status="resolved_known_non_trading_day")], run_timestamp="t1")
    open_items = load_tracker_items(con, open_only=True)
    all_items = load_tracker_items(con, open_only=False)
    assert {i["natural_key"] for i in open_items} == {"k1"}
    assert {i["natural_key"] for i in all_items} == {"k1", "k2"}


def test_load_tracker_items_deserializes_evidence_json(con):
    upsert_tracker_items(con, [_item("k1")], run_timestamp="t1")
    items = load_tracker_items(con)
    assert items[0]["evidence"] == {"k": "v"}
