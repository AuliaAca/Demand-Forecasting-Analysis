"""Unit tests for Phase 09 Part A (data-issue RCA).

Pure-logic tests (rate/lift computation, statement composition) use small
hand-built row lists. `load_flagged_rows_with_context`/`load_baseline_rates`
are exercised against the real fixture warehouse.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.rca.data_issue_evidence import (
    MIN_EVIDENCE_N,
    build_data_issue_rca,
    gather_data_issue_evidence,
    load_baseline_rates,
    load_flagged_rows_with_context,
)
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def warehouse_con(tmp_path, monkeypatch):
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
    yield warehouse_con
    warehouse_con.close()


# --- DB-facing loaders ---------------------------------------------------


def test_load_flagged_rows_with_context_only_returns_flagged_rows(warehouse_con):
    rows = load_flagged_rows_with_context(warehouse_con)
    assert len(rows) == 2  # hand-verified: 1 return + 1 extreme value on this fixture
    assert all(r["is_return"] or r["is_extreme_value"] for r in rows)


def test_load_flagged_rows_with_context_carries_item_family(warehouse_con):
    rows = load_flagged_rows_with_context(warehouse_con)
    assert all(r["item_family"] in {"DAIRY", "GROCERY", "PRODUCE", "UNKNOWN_ITEM"} for r in rows)


def test_load_baseline_rates_returns_rates_between_zero_and_one(warehouse_con):
    baseline = load_baseline_rates(warehouse_con)
    assert 0.0 <= baseline["promotion_rate"] <= 1.0
    assert 0.0 <= baseline["holiday_rate"] <= 1.0


# --- gather_data_issue_evidence / build_data_issue_rca (pure logic) ------


def _row(**kwargs):
    base = {
        "is_return": False, "is_extreme_value": False, "onpromotion": False,
        "item_family": "GROCERY", "store_type": "A", "is_holiday": False, "is_payday": False,
    }
    base.update(kwargs)
    return base


def test_gather_data_issue_evidence_splits_returns_and_extreme_values():
    rows = [
        _row(is_return=True),
        _row(is_extreme_value=True),
        _row(is_return=True, is_extreme_value=True),
    ]
    baseline = {"promotion_rate": 0.1, "holiday_rate": 0.05}
    evidence = gather_data_issue_evidence(rows, baseline)
    assert evidence["returns"]["n"] == 2
    assert evidence["extreme_values"]["n"] == 2


def test_build_data_issue_rca_reports_zero_rows_without_crashing():
    baseline = {"promotion_rate": 0.1, "holiday_rate": 0.05}
    evidence = gather_data_issue_evidence([], baseline)
    records = build_data_issue_rca(evidence)
    assert len(records) == 2
    assert all(r["n"] == 0 for r in records)
    assert all("nothing to investigate" in r["statement"] for r in records)


def test_build_data_issue_rca_flags_elevated_promotion_coincidence():
    # 10 extreme-value rows, 8 of them on a promotion day -> 80% vs a 10%
    # baseline is a strong (8x) lift, well above the association threshold,
    # and n=10 clears the minimum-evidence floor.
    rows = [_row(is_extreme_value=True, onpromotion=(i < 8)) for i in range(10)]
    baseline = {"promotion_rate": 0.1, "holiday_rate": 0.5}
    evidence = gather_data_issue_evidence(rows, baseline)
    records = build_data_issue_rca(evidence)
    extreme = next(r for r in records if r["issue"] == "extreme_values")
    assert extreme["candidate_contributors"]
    assert "associated with" in extreme["statement"]


def test_build_data_issue_rca_reports_cause_unknown_when_nothing_explains_it():
    # 10 extreme-value rows spread evenly across families/promotion/holiday
    # -- nothing should be flagged as a contributor.
    families = ["DAIRY", "GROCERY", "PRODUCE"]
    rows = [_row(is_extreme_value=True, item_family=families[i % 3], onpromotion=False, is_holiday=False) for i in range(10)]
    baseline = {"promotion_rate": 0.0, "holiday_rate": 0.0}
    evidence = gather_data_issue_evidence(rows, baseline)
    records = build_data_issue_rca(evidence)
    extreme = next(r for r in records if r["issue"] == "extreme_values")
    assert extreme["candidate_contributors"] == []
    assert "cause unknown from available evidence" in extreme["statement"]


def test_build_data_issue_rca_ignores_populations_below_min_evidence_n():
    rows = [_row(is_extreme_value=True, onpromotion=True) for _ in range(MIN_EVIDENCE_N - 1)]
    baseline = {"promotion_rate": 0.01, "holiday_rate": 0.01}
    evidence = gather_data_issue_evidence(rows, baseline)
    records = build_data_issue_rca(evidence)
    extreme = next(r for r in records if r["issue"] == "extreme_values")
    assert extreme["candidate_contributors"] == []
