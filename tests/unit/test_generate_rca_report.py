"""Tests for the Phase 09 report generator, using a real RCA run against
the fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.rca.run_rca import run_and_write
from demandflow.reporting.generate_rca_report import render_rca_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def rca_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    convert_all(cfg)

    con = duckdb.connect()
    stats = compute_item_stats(
        con, cfg.paths.parquet_dir / "train.parquet", cfg.paths.parquet_dir / "items.parquet", cfg.dev_scope
    )
    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    con.close()
    dev_scope_csv = tmp_path / "dev_scope_items.csv"
    write_dev_scope_csv(selection, dev_scope_csv)

    db_path = tmp_path / "warehouse.duckdb"
    warehouse_con, checks = build_warehouse(cfg, db_path=db_path, dev_scope_csv_path=dev_scope_csv)
    assert all(c.passed for c in checks)
    warehouse_con.close()

    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    return result["summary"]


def test_render_report_includes_every_section(rca_summary):
    report = render_rca_report(rca_summary, "Test Dataset")
    for heading in [
        "# Root Cause Analysis",
        "## Scope",
        "## Data issues investigated",
        "### Returns",
        "### Extreme Values",
        "## Forecast discrepancies investigated",
        "## Limitations",
    ]:
        assert heading in report


def test_render_report_groups_multiple_findings_for_the_same_segment(rca_summary):
    report = render_rca_report(rca_summary, "Test Dataset")
    # promotion=not_promoted is triggered by both a systematic_bias and a
    # segment_champion_switch finding -- the report groups them under one
    # heading rather than repeating the evidence twice.
    assert report.count("### promotion = not_promoted") == 1
    assert "systematic_bias, model=seasonal_naive" in report
    assert "segment_champion_switch, model=croston" in report


def test_render_report_states_the_dairy_extreme_value_finding(rca_summary):
    report = render_rca_report(rca_summary, "Test Dataset")
    assert "### item_family = DAIRY" in report
    section = report.split("### item_family = DAIRY")[1].split("###")[0]
    assert "extreme values" in section
    assert "associated with" in section


def test_render_report_flags_low_sample_data_issues(rca_summary):
    report = render_rca_report(rca_summary, "Test Dataset")
    assert "Below the n=5 screening minimum" in report


def test_render_report_handles_empty_summary_without_crashing():
    summary = {
        "data_issue_rca": [
            {"issue": "returns", "n": 0, "candidate_contributors": [], "statement": "No returns rows were flagged on this run -- nothing to investigate."},
            {"issue": "extreme_values", "n": 0, "candidate_contributors": [], "statement": "No extreme values rows were flagged on this run -- nothing to investigate."},
        ],
        "forecast_discrepancy_rca": [],
        "forecast_discrepancy_triggers_total": 0,
        "forecast_discrepancy_triggers_investigated": 0,
        "champion_model": None,
    }
    report = render_rca_report(summary, "Test Dataset")
    assert "## Forecast discrepancies investigated" in report
    assert "nothing to investigate" in report
