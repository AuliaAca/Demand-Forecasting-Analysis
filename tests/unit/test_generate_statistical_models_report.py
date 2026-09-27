"""Tests for the Phase 06 report generator, using a real backtest of the
fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.run_statistical_backtest import run_and_write
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_statistical_models_report import render_statistical_models_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def statistical_summary(tmp_path, monkeypatch):
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

    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase06")
    return result["summary"], cfg


def test_render_report_includes_every_section(statistical_summary):
    summary, cfg = statistical_summary
    report = render_statistical_models_report(
        summary, "Test Dataset", cfg.forecasting.horizon_days, cfg.forecasting.season_length_days
    )
    for heading in [
        "# Statistical Models",
        "## Why statistical forecasting was attempted here",
        "## Overall comparison",
        "## By intermittency class",
        "## Final holdout",
    ]:
        assert heading in report


def test_render_report_names_all_five_models(statistical_summary):
    summary, cfg = statistical_summary
    report = render_statistical_models_report(
        summary, "Test Dataset", cfg.forecasting.horizon_days, cfg.forecasting.season_length_days
    )
    for label in ["Naive", "Seasonal Naive", "SES", "Croston", "SBA"]:
        assert label in report


def test_render_report_honestly_states_croston_did_not_win_on_this_fixture(statistical_summary):
    summary, cfg = statistical_summary
    report = render_statistical_models_report(
        summary, "Test Dataset", cfg.forecasting.horizon_days, cfg.forecasting.season_length_days
    )
    # Given the hand-verified fixture result (Seasonal Naive wins overall),
    # the report must take the "did not outperform" branch, not silently
    # claim a win the numbers don't support.
    assert "did **not** outperform the best baseline" in report


def test_render_report_shows_every_intermittency_segment(statistical_summary):
    summary, cfg = statistical_summary
    report = render_statistical_models_report(
        summary, "Test Dataset", cfg.forecasting.horizon_days, cfg.forecasting.season_length_days
    )
    assert "### intermittent" in report
    assert "### lumpy" in report
