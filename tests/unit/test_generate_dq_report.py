"""Tests for the DQ report generator, using real findings from the fixture."""

from pathlib import Path

import duckdb
import pytest

from demandflow.quality.rules import findings_to_dicts, run_all_rules
from demandflow.reporting.generate_dq_report import render_dq_report

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def findings():
    con = duckdb.connect()
    result = run_all_rules(
        con,
        FIXTURE_DIR / "train.csv",
        FIXTURE_DIR / "stores.csv",
        FIXTURE_DIR / "items.csv",
        available_tables=["train", "stores", "items", "holidays_events", "oil", "transactions"],
    )
    con.close()
    return findings_to_dicts(result)


def test_render_dq_report_includes_every_rule_and_its_handling_decision(findings):
    report = render_dq_report(findings, dataset_display_name="Corporación Favorita Grocery Sales Forecasting")
    assert "# Data Quality Report" in report
    assert "## Summary" in report
    assert "## Rule catalog" in report
    for f in findings:
        assert f"`{f['rule_id']}`" in report
        assert f["handling_decision"] in report


def test_render_dq_report_summary_counts_match_findings(findings):
    report = render_dq_report(findings, dataset_display_name="Test Dataset")
    critical_or_high = sum(1 for f in findings if f["severity"] in ("CRITICAL", "HIGH"))
    assert critical_or_high >= 1  # grain_duplicates and orphan_dimension_keys are HIGH here
    assert "| HIGH |" in report
