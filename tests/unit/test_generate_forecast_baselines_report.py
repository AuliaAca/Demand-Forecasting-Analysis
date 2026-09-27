"""Tests for the forecast-baselines report generator, using a real backtest
of the fixture warehouse."""

import datetime
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.backtest import generate_as_of_dates, run_rolling_origin_backtest, summarize_backtest
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_forecast_baselines_report import render_forecast_baselines_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def backtest_summary(tmp_path, monkeypatch):
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

    warehouse_con, checks = build_warehouse(
        cfg, db_path=tmp_path / "warehouse.duckdb", dev_scope_csv_path=dev_scope_csv
    )
    assert all(c.passed for c in checks)
    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    warehouse_con.close()
    return summarize_backtest(records)


def test_render_report_includes_every_section(backtest_summary):
    report = render_forecast_baselines_report(
        backtest_summary, dataset_display_name="Test Dataset",
        horizon_days=5, season_length_days=7, as_of_cadence_days=5,
    )
    for heading in [
        "# Forecast Baselines",
        "## Overall comparison (all as-of dates)",
        "## Final holdout (most recent as-of date)",
        "## By horizon step",
    ]:
        assert heading in report


def test_render_report_states_the_time_aware_validation_rule(backtest_summary):
    report = render_forecast_baselines_report(
        backtest_summary, dataset_display_name="Test Dataset",
        horizon_days=5, season_length_days=7, as_of_cadence_days=5,
    )
    assert "Time-aware validation" in report
    assert "No random train/test split was used" in report


def test_render_report_declares_the_lower_wape_model(backtest_summary):
    report = render_forecast_baselines_report(
        backtest_summary, dataset_display_name="Test Dataset",
        horizon_days=5, season_length_days=7, as_of_cadence_days=5,
    )
    assert "**Lower WAPE: Seasonal Naive.**" in report


def test_render_report_names_both_models_in_the_comparison_table(backtest_summary):
    report = render_forecast_baselines_report(
        backtest_summary, dataset_display_name="Test Dataset",
        horizon_days=5, season_length_days=7, as_of_cadence_days=5,
    )
    assert "| Naive |" in report
    assert "| Seasonal Naive |" in report
