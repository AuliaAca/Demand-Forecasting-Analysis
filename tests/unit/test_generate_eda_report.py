"""Tests for the EDA report generator, using a real run of the fixture warehouse."""

from pathlib import Path

import duckdb
import pytest

from demandflow.analysis.eda import run_full_eda
from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.reporting.generate_eda_report import render_eda_report
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def eda_summary(tmp_path, monkeypatch):
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
    summary = run_full_eda(warehouse_con)
    warehouse_con.close()
    return summary


def test_render_eda_report_includes_every_section(eda_summary):
    report = render_eda_report(eda_summary, dataset_display_name="Test Dataset")
    for heading in [
        "# Exploratory Demand Analysis",
        "## SKUs: velocity, ABC classification, intermittency",
        "## Hubs (stores)",
        "## Categories (family)",
        "## Campaigns (promotion effect)",
        "## Pricing",
        "## Seasonal events",
        "## Trend",
        "## Outliers and demand anomalies, with business context",
    ]:
        assert heading in report


def test_render_eda_report_states_pricing_is_not_analyzed(eda_summary):
    report = render_eda_report(eda_summary, dataset_display_name="Test Dataset")
    assert "**Not analyzed.**" in report
    assert "ADR 0001 D2" in report


def test_render_eda_report_never_asserts_causation_for_flagged_points(eda_summary):
    report = render_eda_report(eda_summary, dataset_display_name="Test Dataset")
    assert "thereby concluded to be errors" in report  # the evidence-based-language caveat is present


def test_render_eda_report_embeds_chart_paths_when_provided(eda_summary):
    report = render_eda_report(
        eda_summary,
        dataset_display_name="Test Dataset",
        chart_paths={"daily_trend": "../reports/phase04/figures/daily_trend.png"},
    )
    assert "![Daily trend](../reports/phase04/figures/daily_trend.png)" in report
