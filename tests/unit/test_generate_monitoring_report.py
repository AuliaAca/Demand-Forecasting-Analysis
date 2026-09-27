"""Tests for the Phase 10 report generator, using a real monitoring run
against the fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.monitoring.run_monitoring import run_and_write
from demandflow.reporting.generate_monitoring_report import render_monitoring_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def monitoring_summary(tmp_path, monkeypatch):
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

    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    return result["summary"]


def test_render_report_includes_every_section(monitoring_summary):
    report = render_monitoring_report(monitoring_summary, "Test Dataset")
    for heading in [
        "# Monitoring",
        "## Scope",
        "## Overall status",
        "## Forecast accuracy",
        "## Forecast deterioration",
        "## Data quality",
        "## Anomalies",
        "## Limitations",
    ]:
        assert heading in report


def test_render_report_states_the_real_overall_status(monitoring_summary):
    report = render_monitoring_report(monitoring_summary, "Test Dataset")
    assert "## Overall status: **BREACH**" in report


def test_render_report_names_driving_dq_rules(monitoring_summary):
    report = render_monitoring_report(monitoring_summary, "Test Dataset")
    assert "grain_duplicates" in report
    assert "orphan_dimension_keys" in report


def test_render_report_lists_the_recent_anomaly_table(monitoring_summary):
    report = render_monitoring_report(monitoring_summary, "Test Dataset")
    assert "| Date | Total units | z-score |" in report
    assert "2013-01-20" in report


def test_render_report_explains_the_phase_11_scope_boundary(monitoring_summary):
    report = render_monitoring_report(monitoring_summary, "Test Dataset")
    assert "Phase 11" in report


def test_render_report_handles_unknown_signals_without_crashing():
    summary = {
        "champion_model": None,
        "overall_status": "UNKNOWN",
        "signals": [
            {"signal": "forecast_accuracy", "status": "UNKNOWN", "champion_model": None, "wape": None, "reason": "No champion model with a computable overall WAPE was available."},
            {"signal": "forecast_deterioration", "status": "UNKNOWN", "champion_model": None, "reason": "No champion model identified."},
            {"signal": "data_quality", "status": "UNKNOWN", "reason": "No DQ findings were available to roll up."},
            {"signal": "anomalies", "status": "UNKNOWN", "reason": "No daily totals were available."},
        ],
        "dq_findings": [],
    }
    report = render_monitoring_report(summary, "Test Dataset")
    assert "## Overall status: **UNKNOWN**" in report
