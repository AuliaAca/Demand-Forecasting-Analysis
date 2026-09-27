"""Tests for the Phase 09 RCA orchestrator, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the investigation (see docs/phase_reports/phase09.md),
not just asserting "it runs without error" -- the same discipline as every
previous phase.
"""

import json
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.rca.run_rca import DISCREPANCY_FINDING_CATEGORIES, run_and_write
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


def test_run_and_write_produces_two_data_issue_records(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    data_issues = result["summary"]["data_issue_rca"]
    assert {r["issue"] for r in data_issues} == {"returns", "extreme_values"}
    assert all(r["n"] == 1 for r in data_issues)  # hand-verified: 1 return + 1 extreme value on this fixture


def test_run_and_write_investigates_every_segment_shaped_finding(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    summary = result["summary"]

    assert summary["champion_model"] == "seasonal_naive"  # matches Phase 08's own hand-verified result
    assert summary["forecast_discrepancy_triggers_total"] == 14  # matches Phase 08's hand-verified finding count
    assert summary["forecast_discrepancy_triggers_investigated"] == 14
    for record in summary["forecast_discrepancy_rca"]:
        assert record["source_finding_category"] in DISCREPANCY_FINDING_CATEGORIES


def test_run_and_write_finds_the_dairy_extreme_value_association(built_warehouse):
    # Honest empirical result on this fixture: DAIRY's under-forecast bias
    # coincides with an elevated extreme-value rate -- a genuine, specific
    # finding, not a generic "cause unknown" for every segment.
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    dairy = next(
        r for r in result["summary"]["forecast_discrepancy_rca"]
        if r["dimension"] == "item_family" and r["segment"] == "DAIRY"
    )
    assert "extreme values" in dairy["statement"]
    assert "associated with" in dairy["statement"]


def test_run_and_write_reports_cause_unknown_for_payday_and_holiday_segments(built_warehouse):
    # Honest empirical result: no elevated DQ-flag rate and no diverging
    # trend explains the holiday/payday-related discrepancies on this
    # fixture -- reported as unexplained rather than forced into a finding.
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    for dimension, segment in [("holiday", "non_holiday"), ("payday", "non_payday")]:
        record = next(
            r for r in result["summary"]["forecast_discrepancy_rca"]
            if r["dimension"] == dimension and r["segment"] == segment
        )
        assert "cause unknown from available evidence" in record["statement"]


def test_run_and_write_output_is_json_serializable(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    json.dumps(result["summary"])


def test_run_and_write_writes_the_summary_file(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase09")
    assert result["summary_path"].exists()
    on_disk = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert on_disk["champion_model"] == result["summary"]["champion_model"]


def test_run_and_write_raises_a_clear_error_without_a_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        run_and_write(cfg, db_path=tmp_path / "does_not_exist.duckdb", out_dir=tmp_path / "phase09")
