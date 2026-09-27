"""Tests for the Phase 08 evaluation orchestrator, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the evaluation (see docs/phase_reports/phase08.md), not
just asserting "it runs without error" -- the same discipline as every
previous phase.
"""

import json
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.evaluation.run_evaluation import run_and_write
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


def test_run_and_write_reproduces_phase06s_overall_wape(built_warehouse):
    # run_evaluation.py rebuilds fct_forecast with the exact same 5-model
    # rolling-origin backtest as Phase 06 (same as-of schedule, same cfg) --
    # these numbers must match test_statistical_backtest.py's hand-verified
    # values exactly, since it is the same computation.
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    overall = result["summary"]["overall_by_model"]

    assert overall["naive"]["wape"] == pytest.approx(1.0733590733590734)
    assert overall["seasonal_naive"]["wape"] == pytest.approx(0.9078947368421053)
    assert overall["ses"]["wape"] == pytest.approx(1.2039383044934178)
    assert overall["croston"]["wape"] == pytest.approx(1.4528090525550303)
    assert overall["sba"]["wape"] == pytest.approx(1.42051609027477)
    assert result["summary"]["champion_model"] == "seasonal_naive"


def test_run_and_write_populates_every_dimension(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    by_dimension = result["summary"]["by_dimension"]

    assert set(by_dimension) == {
        "item_family", "store_type", "cluster", "promotion", "holiday", "payday",
        "horizon_step", "as_of_date", "intermittency_class",
    }
    assert set(by_dimension["item_family"]) == {"DAIRY", "GROCERY", "PRODUCE"}
    assert set(by_dimension["store_type"]) == {"A", "B", "C"}
    assert set(by_dimension["promotion"]) <= {"promoted", "not_promoted"}


def test_run_and_write_by_item_family_matches_hand_verified_wape(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    dairy = result["summary"]["by_dimension"]["item_family"]["DAIRY"]

    assert dairy["naive"]["wape"] == pytest.approx(1.0)
    assert dairy["seasonal_naive"]["wape"] == pytest.approx(0.9638554216867470)
    assert dairy["naive"]["n"] == 39


def test_run_and_write_finds_a_segment_champion_switch(built_warehouse):
    # Honest empirical result on this fixture: in the "not_promoted" segment,
    # Croston beats the overall champion (Seasonal Naive) -- exactly the
    # kind of actionable, segment-specific recommendation Phase 08 exists
    # to surface (CLAUDE.md Section 3.3).
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    findings = result["summary"]["findings"]

    switches = [f for f in findings if f["category"] == "segment_champion_switch"]
    assert any(
        f["dimension"] == "promotion" and f["segment"] == "not_promoted" and f["recommended_model"] == "croston"
        for f in switches
    )


def test_run_and_write_flags_seasonal_naives_network_wide_underforecast_bias(built_warehouse):
    # Honest empirical result: the overall champion (Seasonal Naive) has a
    # large negative bias overall (-63.2%), and it recurs across many
    # segments -- not just one or two.
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    summary = result["summary"]

    assert summary["overall_by_model"]["seasonal_naive"]["forecast_bias"] == pytest.approx(-0.631578947368421)
    bias_findings = [f for f in summary["findings"] if f["category"] == "systematic_bias"]
    assert len(bias_findings) >= 10
    assert all(f["model"] == "seasonal_naive" for f in bias_findings)


def test_run_and_write_output_is_json_serializable(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    json.dumps(result["summary"])


def test_run_and_write_writes_the_summary_file(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase08")
    assert result["summary_path"].exists()
    on_disk = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert on_disk["champion_model"] == result["summary"]["champion_model"]


def test_run_and_write_raises_a_clear_error_without_a_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        run_and_write(cfg, db_path=tmp_path / "does_not_exist.duckdb", out_dir=tmp_path / "phase08")
