"""Tests for the Phase 07 report generator, using a real backtest of the
fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.run_ml_backtest import run_and_write
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_ml_report import render_ml_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def ml_summary(tmp_path, monkeypatch):
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

    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    return result["summary"], cfg


def test_render_report_includes_every_section(ml_summary):
    summary, cfg = ml_summary
    report = render_ml_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    for heading in ["# Machine Learning Forecasting", "## Train/holdout split", "## Holdout comparison", "## Feature importance"]:
        assert heading in report


def test_render_report_states_lightgbm_wins_on_this_fixture(ml_summary):
    summary, cfg = ml_summary
    report = render_ml_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    assert "**Lowest WAPE on this holdout: LightGBM.**" in report
    assert "is associated with lower error than" in report
    assert "encouraging, not conclusive" in report


def test_render_report_names_the_jd_bonus_status(ml_summary):
    summary, cfg = ml_summary
    report = render_ml_report(summary, "Test Dataset", cfg.forecasting.horizon_days)
    assert "JD bonus item, not a mandatory requirement" in report


def test_render_report_handles_untrained_model_without_crashing():
    summary = {
        "as_of_dates_used": ["2013-01-07", "2013-01-14"],
        "holdout_as_of_date": "2013-01-14",
        "training_rows": 3,
        "holdout_rows": 10,
        "holdout_scored_rows": 2,
        "model_trained": False,
        "insufficient_training_data": True,
        "min_training_rows_required": 10,
        "holdout_by_model": {},
        "lower_wape_model": None,
        "feature_importance": None,
    }
    report = render_ml_report(summary, "Test Dataset", 14)
    assert "## Result: model not trained" in report
    assert "not evaluable" in report
