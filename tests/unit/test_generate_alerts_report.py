"""Tests for the Phase 11 report generator, using real alerts/tracker runs
against the fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.alerts.run_alerts import run_and_write
from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_alerts_report import render_alerts_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def built_warehouse(tmp_path, monkeypatch):
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
    return cfg, db_path, tmp_path


def test_render_report_includes_every_section_on_first_run(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    report = render_alerts_report(result["summary"], "Test Dataset")
    for heading in [
        "# Alerts & Discrepancy Tracker",
        "## Scope",
        "## Alerts fired this run",
        "## Run history",
        "## Discrepancy tracker — open items",
        "## Limitations",
    ]:
        assert heading in report


def test_render_report_lists_fired_alerts_on_first_run(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    report = render_alerts_report(result["summary"], "Test Dataset")
    assert "| data_quality |" in report
    assert "| anomalies |" in report


def test_render_report_states_no_alerts_on_unchanged_second_run(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run1")
    result2 = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run2")
    report = render_alerts_report(result2["summary"], "Test Dataset")
    assert "No alert fired this run" in report
    assert "| Run # | Generated at | Overall status |" in report


def test_render_report_lists_open_tracker_items_with_times_seen(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run1")
    result2 = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run2")
    report = render_alerts_report(result2["summary"], "Test Dataset")
    assert "calendar_gap" in report
    assert "| calendar_gap | warning | No sales rows exist for 2013-01-10" in report


def test_render_report_handles_empty_tracker_without_crashing():
    summary = {
        "run_seq": 1, "generated_at": "t1", "overall_status": "OK", "champion_model": "naive",
        "alerts": [], "recent_history": [{"run_seq": 1, "generated_at": "t1", "overall_status": "OK"}],
        "tracker_upsert_result": {"inserted": 0, "updated": 0}, "open_tracker_items": [],
    }
    report = render_alerts_report(summary, "Test Dataset")
    assert "No open tracker items on this run." in report
