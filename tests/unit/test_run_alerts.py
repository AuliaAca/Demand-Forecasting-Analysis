"""Tests for the Phase 11 alerts/tracker orchestrator, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the check twice (see docs/phase_reports/phase11.md),
not just asserting "it runs without error" -- the same discipline as every
previous phase. Running it a second time against the unchanged warehouse is
this phase's key correctness property: zero alerts, per the "avoid
unnecessary alert noise" objective.
"""

import json
from pathlib import Path

import duckdb
import pytest

from demandflow.alerts.run_alerts import run_and_write
from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
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


def test_first_run_fires_alerts_for_non_ok_signals(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    summary = result["summary"]

    assert summary["run_seq"] == 1
    assert summary["overall_status"] == "BREACH"
    fired_signals = {a["signal"] for a in summary["alerts"]}
    assert fired_signals == {"data_quality", "anomalies"}  # hand-verified: these two are non-OK on this fixture
    assert all(a["direction"] == "new" for a in summary["alerts"])


def test_second_identical_run_fires_zero_alerts(built_warehouse):
    # The key "avoid unnecessary alert noise" guarantee: re-running against
    # an unchanged warehouse must not re-alert on the same, already-known
    # BREACH/WARN state.
    cfg, db_path, tmp_path = built_warehouse
    run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run1")
    result2 = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run2")

    assert result2["summary"]["run_seq"] == 2
    assert result2["summary"]["alerts"] == []


def test_tracker_items_persist_and_increment_across_runs(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result1 = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run1")
    assert result1["summary"]["tracker_upsert_result"] == {"inserted": 4, "updated": 0}
    items1 = {i["natural_key"]: i["times_seen"] for i in result1["summary"]["open_tracker_items"]}

    result2 = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11_run2")
    assert result2["summary"]["tracker_upsert_result"] == {"inserted": 0, "updated": 4}
    items2 = {i["natural_key"]: i["times_seen"] for i in result2["summary"]["open_tracker_items"]}

    assert set(items1) == set(items2)
    for key in items1:
        assert items2[key] == items1[key] + 1


def test_calendar_gap_tracker_item_matches_the_hand_verified_fixture_gap(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    gap_items = [i for i in result["summary"]["open_tracker_items"] if i["category"] == "calendar_gap"]
    assert len(gap_items) == 1
    assert gap_items[0]["evidence"]["date"] == "2013-01-10"
    assert gap_items[0]["evidence"]["matches_known_non_trading_day"] is False


def test_run_and_write_output_is_json_serializable(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    json.dumps(result["summary"])


def test_run_and_write_writes_the_summary_file(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase11")
    assert result["summary_path"].exists()
    on_disk = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert on_disk["run_seq"] == result["summary"]["run_seq"]


def test_run_and_write_raises_a_clear_error_without_a_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        run_and_write(cfg, db_path=tmp_path / "does_not_exist.duckdb", out_dir=tmp_path / "phase11")
