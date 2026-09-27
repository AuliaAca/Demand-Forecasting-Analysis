"""Tests for the Phase 10 monitoring orchestrator, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the check (see docs/phase_reports/phase10.md), not
just asserting "it runs without error" -- the same discipline as every
previous phase.
"""

import json
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.monitoring.run_monitoring import run_and_write
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


def test_run_and_write_produces_all_four_signals(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    signal_names = {s["signal"] for s in result["summary"]["signals"]}
    assert signal_names == {"forecast_accuracy", "forecast_deterioration", "data_quality", "anomalies"}


def test_run_and_write_matches_hand_verified_statuses_on_this_fixture(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    summary = result["summary"]
    by_signal = {s["signal"]: s for s in summary["signals"]}

    assert summary["champion_model"] == "seasonal_naive"
    assert by_signal["forecast_accuracy"]["status"] == "OK"
    assert by_signal["forecast_accuracy"]["wape"] == pytest.approx(0.9078947368421053)
    assert by_signal["forecast_deterioration"]["status"] == "OK"
    assert by_signal["data_quality"]["status"] == "BREACH"
    assert set(by_signal["data_quality"]["driving_rules"]) == {"grain_duplicates", "orphan_dimension_keys"}
    assert by_signal["anomalies"]["status"] == "WARN"
    assert by_signal["anomalies"]["recent_anomaly_count"] == 1
    # Overall status must be the worst of the four -- BREACH, driven by data quality.
    assert summary["overall_status"] == "BREACH"


def test_run_and_write_includes_the_raw_dq_findings(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    assert len(result["summary"]["dq_findings"]) == 8


def test_run_and_write_does_not_mutate_fct_forecast(built_warehouse):
    # Monitoring only needs the backtest's in-memory records; unlike Phase
    # 08/09 it has no reason to write to fct_forecast, so the mart should
    # be untouched (or absent) after a monitoring run.
    cfg, db_path, tmp_path = built_warehouse
    run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    con = duckdb.connect(str(db_path))
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    con.close()
    assert "fct_forecast" not in tables


def test_run_and_write_output_is_json_serializable(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    json.dumps(result["summary"])


def test_run_and_write_writes_the_summary_file(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase10")
    assert result["summary_path"].exists()
    on_disk = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert on_disk["overall_status"] == result["summary"]["overall_status"]


def test_run_and_write_raises_a_clear_error_without_a_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        run_and_write(cfg, db_path=tmp_path / "does_not_exist.duckdb", out_dir=tmp_path / "phase10")
