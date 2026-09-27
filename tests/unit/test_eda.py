"""Tests for the Phase 04 EDA functions, against the fixture warehouse.

Every assertion below was hand-verified against tests/fixtures/favorita_sample/
by actually running the analysis and checking the numbers (see
docs/phase_reports/phase04.md), not just asserting "it runs without error".
"""

import shutil
from pathlib import Path

import duckdb
import pytest

from demandflow.analysis.eda import (
    ANOMALY_Z_THRESHOLD,
    category_summary,
    extreme_value_context,
    hub_summary,
    network_anomalies,
    promotion_effect,
    run_full_eda,
    seasonal_event_effect,
    sku_velocity_and_intermittency,
    trend_summary,
)
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


def test_sku_velocity_covers_every_item_including_the_orphan(warehouse_con):
    rows = sku_velocity_and_intermittency(warehouse_con)
    item_nbrs = {r["item_nbr"] for r in rows}
    assert item_nbrs == {100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 999}
    assert len(rows) == 11


def test_sku_top_item_is_104_driven_by_the_planted_extreme_value(warehouse_con):
    rows = sku_velocity_and_intermittency(warehouse_con)
    top = rows[0]
    assert top["item_nbr"] == 104
    assert top["total_unit_sales"] == pytest.approx(86.0)
    assert top["abc_class"] == "A"
    assert top["intermittency_class"] == "lumpy"  # ADI and CV2 both above threshold


def test_abc_classes_partition_all_items_by_cumulative_share(warehouse_con):
    rows = sku_velocity_and_intermittency(warehouse_con)
    by_class = {c: [r["item_nbr"] for r in rows if r["abc_class"] == c] for c in "ABC"}
    assert len(by_class["A"]) + len(by_class["B"]) + len(by_class["C"]) == 11
    # cumulative share is monotonically non-decreasing in rank order and ends at 1.0
    shares = [r["cumulative_share_of_volume"] for r in rows]
    assert shares == sorted(shares)
    assert shares[-1] == pytest.approx(1.0)


def test_orphan_item_gets_a_defined_classification_not_a_crash(warehouse_con):
    rows = sku_velocity_and_intermittency(warehouse_con)
    orphan = next(r for r in rows if r["item_nbr"] == 999)
    assert orphan["active_days"] == 1
    assert orphan["nonzero_days"] == 1
    assert orphan["intermittency_class"] == "smooth"  # single observation: ADI=1, CV2=0


def test_hub_summary_covers_all_five_stores_store2_highest(warehouse_con):
    rows = hub_summary(warehouse_con)
    assert {r["store_nbr"] for r in rows} == {1, 2, 3, 4, 5}
    assert rows[0]["store_nbr"] == 2
    assert rows[0]["total_unit_sales"] == pytest.approx(108.5)


def test_category_summary_excludes_the_orphan_item(warehouse_con):
    rows = category_summary(warehouse_con)
    families = {r["family"] for r in rows}
    assert families == {"GROCERY", "DAIRY", "PRODUCE"}
    total = sum(r["total_unit_sales"] for r in rows)
    # Grand total (235.5) minus the orphan item's 2.0 units (item 999 has no
    # family -- it's excluded by the INNER JOIN to dim_sku).
    assert total == pytest.approx(233.5)


def test_promotion_effect_excludes_unknown_and_returns(warehouse_con):
    result = promotion_effect(warehouse_con)
    assert result["rows_excluded_unknown_promotion"] == 5
    assert result["rows_excluded_returns"] == 1
    counted = sum(r["n"] for r in result["by_promotion_status"])
    assert counted == 51 - 5 - 1  # total stg_sales rows minus both exclusions
    assert result["uplift_pct_promoted_vs_not"] == pytest.approx(-0.19473876507124577)


def test_seasonal_event_effect_row_counts_reconcile(warehouse_con):
    result = seasonal_event_effect(warehouse_con)
    assert sum(r["n"] for r in result["holiday_effect"]) == 50  # 51 - 1 return
    assert sum(r["n"] for r in result["day_of_week"]) == 50
    assert sum(r["n"] for r in result["payday_effect"]) == 50


def test_trend_summary_direction_and_window(warehouse_con):
    result = trend_summary(warehouse_con)
    assert len(result["daily_totals"]) == 20  # 2013-01-01..2013-01-20
    assert result["rolling_window_used"] == 7
    assert result["trend_direction"] == "increasing"
    assert result["ols_slope_per_day"] > 0


def test_network_anomalies_flags_the_extreme_value_day(warehouse_con):
    trend = trend_summary(warehouse_con)
    anomalies = network_anomalies(trend["daily_totals"])
    assert len(anomalies) == 1
    assert anomalies[0]["date"] == "2013-01-20"
    assert anomalies[0]["z_score"] == pytest.approx(4.140152973159024)
    assert anomalies[0]["z_score"] > ANOMALY_Z_THRESHOLD  # well past the flagging threshold, not borderline


def test_extreme_value_context_has_both_planted_points_with_no_promo_or_holiday_link(warehouse_con):
    rows = extreme_value_context(warehouse_con)
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {16, 52}
    assert by_id[16]["is_return"] is True
    assert by_id[52]["is_extreme_value"] is True
    # Neither planted point coincides with a promotion or a holiday in this fixture.
    for r in rows:
        assert r["onpromotion"] is False
        assert r["is_holiday"] is False


def test_run_full_eda_documents_pricing_as_not_analyzed(warehouse_con):
    summary = run_full_eda(warehouse_con)
    assert summary["pricing"]["analyzed"] is False
    assert "ADR 0001 D2" in summary["pricing"]["reason"]
    # Every top-level section from the individual functions is present.
    assert set(summary.keys()) == {
        "sku", "hubs", "categories", "promotion_effect", "seasonal_events",
        "trend", "extreme_value_context", "network_anomalies", "pricing",
    }


def test_run_full_eda_output_is_json_serializable(warehouse_con):
    import json

    summary = run_full_eda(warehouse_con)
    json.dumps(summary)  # raises if any value (e.g. a raw datetime.date) slipped through
