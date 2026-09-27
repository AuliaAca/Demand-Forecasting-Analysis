"""Tests for the Phase 08 report generator, using a real evaluation run
against the fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.evaluation.run_evaluation import run_and_write
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_evaluation_report import render_evaluation_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def evaluation_summary(tmp_path, monkeypatch):
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

    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    return result["summary"], cfg


def test_render_report_includes_every_section(evaluation_summary):
    summary, cfg = evaluation_summary
    report = render_evaluation_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    for heading in [
        "# Forecast Evaluation",
        "## Scope",
        "## Overall comparison",
        "## By Category (item family)",
        "## By Hub (store type)",
        "## By Campaign (promotion status)",
        "## Accuracy by horizon step",
        "## Accuracy over time (as-of date trend)",
        "## Findings and recommendations",
        "## Limitations",
    ]:
        assert heading in report


def test_render_report_names_the_real_champion_model(evaluation_summary):
    summary, cfg = evaluation_summary
    report = render_evaluation_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    assert "**Lowest overall WAPE: Seasonal Naive.**" in report


def test_render_report_states_a_segment_champion_switch(evaluation_summary):
    summary, cfg = evaluation_summary
    report = render_evaluation_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    assert "is associated with lower error than the overall champion" in report


def test_render_report_explains_why_lightgbm_is_out_of_scope(evaluation_summary):
    summary, cfg = evaluation_summary
    report = render_evaluation_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    assert "LightGBM" in report
    assert "single-final-holdout design" in report
    assert "| LightGBM |" not in report  # never scored in any per-dimension table


def test_render_report_handles_no_findings_without_crashing():
    summary = {
        "as_of_dates_used": ["2013-01-07"],
        "total_records": 10,
        "total_scored_records": 5,
        "overall_by_model": {"naive": {"n": 5, "wape": 1.0, "mae": 1.0, "forecast_bias": 0.0}},
        "champion_model": "naive",
        "by_dimension": {},
        "champions_by_dimension": {},
        "accuracy_trend_by_model": {},
        "findings": [],
    }
    report = render_evaluation_report(summary, "Test Dataset", 14)
    assert "No finding crossed this phase's screening thresholds" in report
    assert "## Findings and recommendations" in report
