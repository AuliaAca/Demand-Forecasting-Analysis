"""Unit tests for Phase 09 Part B (forecast-discrepancy RCA).

Pure-logic tests (segment membership, DQ-flag rates, trend divergence,
statement composition) use small hand-built rows. `segment_trend_slope`/
`network_trend_slope` are exercised against the real fixture warehouse.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.rca.discrepancy_evidence import (
    MIN_EVIDENCE_N,
    build_discrepancy_rca,
    dq_flag_rates,
    network_trend_slope,
    rows_for_segment,
    segment_trend_slope,
    unique_triples,
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


def _row(store_nbr, item_nbr, target_date, model="naive", **kwargs):
    base = {
        "store_nbr": store_nbr, "item_nbr": item_nbr, "target_date": target_date, "model": model,
        "item_family": "GROCERY", "store_type": "A", "cluster": 1,
        "target_onpromotion": False, "target_promotion_unknown": False,
        "target_is_holiday": False, "target_is_payday": False,
        "target_is_extreme_value": False, "target_is_return": False, "target_is_imputed_zero": False,
        "horizon_step": 1, "as_of_date": "2013-01-07",
    }
    base.update(kwargs)
    return base


# --- unique_triples / dq_flag_rates --------------------------------------


def test_unique_triples_collapses_duplicate_model_rows():
    rows = [_row(1, 100, "2013-01-10", model=m) for m in ["naive", "seasonal_naive", "ses", "croston", "sba"]]
    assert len(unique_triples(rows)) == 1


def test_dq_flag_rates_computed_over_distinct_triples_not_raw_rows():
    # Same triple duplicated 5x (once per model), flagged as extreme once --
    # the rate must be 1.0 (1 flagged triple / 1 distinct triple), not
    # diluted or inflated by the 5x row duplication.
    rows = [_row(1, 100, "2013-01-10", model=m, target_is_extreme_value=True) for m in ["naive", "seasonal_naive", "ses", "croston", "sba"]]
    rates = dq_flag_rates(rows)
    assert rates["n"] == 1
    assert rates["extreme_value_rate"] == pytest.approx(1.0)


def test_dq_flag_rates_empty_input_reports_none():
    rates = dq_flag_rates([])
    assert rates == {"n": 0, "extreme_value_rate": None, "return_rate": None, "imputed_zero_rate": None}


# --- rows_for_segment ------------------------------------------------------


def test_rows_for_segment_filters_by_item_family():
    rows = [_row(1, 100, "2013-01-10", item_family="DAIRY"), _row(1, 101, "2013-01-10", item_family="GROCERY")]
    segment_rows = rows_for_segment(rows, "item_family", "DAIRY")
    assert len(segment_rows) == 1
    assert segment_rows[0]["item_nbr"] == 100


def test_rows_for_segment_filters_by_promotion_key():
    rows = [
        _row(1, 100, "2013-01-10", target_onpromotion=True),
        _row(1, 101, "2013-01-10", target_onpromotion=False),
    ]
    assert len(rows_for_segment(rows, "promotion", "promoted")) == 1
    assert len(rows_for_segment(rows, "promotion", "not_promoted")) == 1


def test_rows_for_segment_uses_intermittency_class_lookup():
    rows = [_row(1, 100, "2013-01-10"), _row(1, 101, "2013-01-10")]
    item_to_class = {100: "lumpy", 101: "smooth"}
    segment_rows = rows_for_segment(rows, "intermittency_class", "lumpy", item_to_class)
    assert len(segment_rows) == 1
    assert segment_rows[0]["item_nbr"] == 100


def test_rows_for_segment_returns_empty_for_unknown_dimension():
    rows = [_row(1, 100, "2013-01-10")]
    assert rows_for_segment(rows, "not_a_real_dimension", "x") == []


# --- segment_trend_slope / network_trend_slope (DB-facing) ---------------


def test_network_trend_slope_returns_a_float(warehouse_con):
    slope = network_trend_slope(warehouse_con)
    assert isinstance(slope, float)


def test_segment_trend_slope_matches_a_manual_query_for_item_family(warehouse_con):
    slope = segment_trend_slope(warehouse_con, "item_family", "DAIRY")
    manual_rows = warehouse_con.execute(
        """
        SELECT f.date, SUM(f.unit_sales) FROM fct_sales_daily f
        JOIN dim_sku sku ON sku.item_nbr = f.item_nbr
        WHERE sku.family = 'DAIRY' GROUP BY f.date ORDER BY f.date
        """
    ).fetchall()
    n = len(manual_rows)
    xs = list(range(n))
    ys = [r[1] for r in manual_rows]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    expected = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    assert slope == pytest.approx(expected)


def test_segment_trend_slope_returns_none_for_a_row_context_dimension(warehouse_con):
    assert segment_trend_slope(warehouse_con, "promotion", "promoted") is None
    assert segment_trend_slope(warehouse_con, "horizon_step", "1") is None


def test_segment_trend_slope_uses_item_list_for_intermittency_class(warehouse_con):
    slope = segment_trend_slope(warehouse_con, "intermittency_class", "lumpy", item_nbrs=[104])
    manual = warehouse_con.execute(
        "SELECT date, SUM(unit_sales) FROM fct_sales_daily WHERE item_nbr = 104 GROUP BY date ORDER BY date"
    ).fetchall()
    n = len(manual)
    xs = list(range(n))
    ys = [r[1] for r in manual]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    expected = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    assert slope == pytest.approx(expected)


# --- build_discrepancy_rca (pure logic) -----------------------------------


def _finding(dimension="item_family", segment="DAIRY", category="systematic_bias", model="seasonal_naive"):
    return {
        "category": category, "dimension": dimension, "segment": segment, "model": model,
        "statement": f"{model} systematically under-forecasts in {dimension}={segment}.",
    }


def test_build_discrepancy_rca_reports_dq_flag_evidence_when_elevated():
    evidence = {
        "dimension": "item_family", "segment": "DAIRY",
        "dq_flag_rates": {"n": 10, "extreme_value_rate": 0.5, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "baseline_dq_flag_rates": {"n": 100, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "segment_trend_slope": None,
        "network_trend_slope": 0.5,
    }
    record = build_discrepancy_rca(_finding(), evidence)
    assert record["candidate_contributors"]
    assert "extreme values" in record["statement"]
    assert "associated with" in record["statement"]


def test_build_discrepancy_rca_reports_trend_divergence():
    evidence = {
        "dimension": "item_family", "segment": "GROCERY",
        "dq_flag_rates": {"n": 10, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "baseline_dq_flag_rates": {"n": 100, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "segment_trend_slope": -2.0,
        "network_trend_slope": 1.0,
    }
    record = build_discrepancy_rca(_finding(segment="GROCERY"), evidence)
    assert "diverges from the network-wide trend" in record["statement"]


def test_build_discrepancy_rca_reports_cause_unknown_when_nothing_explains_it():
    evidence = {
        "dimension": "holiday", "segment": "non_holiday",
        "dq_flag_rates": {"n": 10, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "baseline_dq_flag_rates": {"n": 100, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "segment_trend_slope": None,
        "network_trend_slope": 1.0,
    }
    record = build_discrepancy_rca(_finding(dimension="holiday", segment="non_holiday"), evidence)
    assert record["candidate_contributors"] == []
    assert "cause unknown from available evidence" in record["statement"]


def test_build_discrepancy_rca_ignores_dq_evidence_below_min_n():
    evidence = {
        "dimension": "item_family", "segment": "DAIRY",
        "dq_flag_rates": {"n": MIN_EVIDENCE_N - 1, "extreme_value_rate": 0.9, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "baseline_dq_flag_rates": {"n": 100, "extreme_value_rate": 0.1, "return_rate": 0.0, "imputed_zero_rate": 0.5},
        "segment_trend_slope": None,
        "network_trend_slope": 1.0,
    }
    record = build_discrepancy_rca(_finding(), evidence)
    assert record["candidate_contributors"] == []
