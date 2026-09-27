"""Unit tests for the Phase 08 segment-evaluation building blocks.

Pure-logic tests (grouping, champion selection, trend slope, findings) use
small hand-built rows/summaries so the expected result can be worked out by
hand. `load_scored_forecasts_with_context` is exercised against the real
fixture warehouse, the same pattern as every previous phase's DB-facing
tests.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.evaluation.segment_evaluation import (
    MIN_SEGMENT_SCORED_N,
    accuracy_trend_by_model,
    champions_by_dimension,
    evaluate_by_dimension,
    evaluate_by_horizon_step,
    evaluate_by_promotion,
    identify_findings,
    load_scored_forecasts_with_context,
)
from demandflow.forecasting.backtest import (
    generate_as_of_dates,
    load_fct_forecast,
    run_rolling_origin_backtest,
)
from demandflow.forecasting.run_statistical_backtest import build_extended_models
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
def scored_rows(tmp_path, monkeypatch):
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

    as_of_dates = generate_as_of_dates(
        *warehouse_con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone(),
        cadence_days=cfg.forecasting.as_of_cadence_days,
        min_history_days=cfg.forecasting.min_history_days,
    )
    models = build_extended_models(cfg.forecasting.season_length_days)
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=cfg.forecasting.horizon_days, models=models)
    load_fct_forecast(warehouse_con, records)

    rows = load_scored_forecasts_with_context(warehouse_con)
    warehouse_con.close()
    return rows


# --- load_scored_forecasts_with_context -------------------------------------


def test_load_scored_forecasts_with_context_only_returns_scored_rows(scored_rows):
    assert len(scored_rows) == 465  # hand-verified: matches run_evaluation's total_scored_records on this fixture
    required_keys = {
        "as_of_date", "horizon_step", "target_date", "store_nbr", "item_nbr", "model",
        "forecast", "actual", "item_family", "store_type", "cluster",
        "target_onpromotion", "target_promotion_unknown", "target_is_holiday", "target_is_payday",
    }
    assert required_keys <= set(scored_rows[0])


def test_load_scored_forecasts_with_context_carries_real_dimension_values(scored_rows):
    families = {r["item_family"] for r in scored_rows}
    store_types = {r["store_type"] for r in scored_rows}
    assert families == {"DAIRY", "GROCERY", "PRODUCE"}
    assert store_types == {"A", "B", "C"}


# --- evaluate_by_dimension ----------------------------------------------------


def _row(model, actual, forecast, **extra):
    base = {"model": model, "actual": actual, "forecast": forecast}
    base.update(extra)
    return base


def test_evaluate_by_dimension_groups_and_summarizes():
    rows = [
        _row("naive", 10.0, 8.0, segment="a"),
        _row("naive", 10.0, 10.0, segment="b"),
        _row("seasonal_naive", 10.0, 9.0, segment="a"),
    ]
    result = evaluate_by_dimension(rows, lambda r: r["segment"])
    assert set(result) == {"a", "b"}
    assert result["a"]["naive"]["n"] == 1
    assert result["a"]["naive"]["wape"] == pytest.approx(0.2)
    assert result["b"]["naive"]["wape"] == pytest.approx(0.0)
    assert "seasonal_naive" not in result["b"]


def test_evaluate_by_dimension_excludes_none_keys():
    rows = [_row("naive", 10.0, 8.0, segment="a"), _row("naive", 5.0, 5.0, segment=None)]
    result = evaluate_by_dimension(rows, lambda r: r["segment"])
    assert set(result) == {"a"}


def test_evaluate_by_horizon_step_sorts_numerically_not_lexically():
    rows = [_row("naive", 1.0, 1.0, horizon_step=h) for h in [1, 2, 10, 11, 3]]
    result = evaluate_by_horizon_step(rows)
    assert list(result) == ["1", "2", "3", "10", "11"]


def test_evaluate_by_promotion_excludes_unknown_rows():
    rows = [
        _row("naive", 10.0, 8.0, target_onpromotion=True, target_promotion_unknown=False),
        _row("naive", 10.0, 8.0, target_onpromotion=False, target_promotion_unknown=False),
        _row("naive", 10.0, 8.0, target_onpromotion=False, target_promotion_unknown=True),
    ]
    result = evaluate_by_promotion(rows)
    assert set(result) == {"promoted", "not_promoted"}
    assert result["promoted"]["naive"]["n"] == 1
    assert result["not_promoted"]["naive"]["n"] == 1


# --- champions_by_dimension ---------------------------------------------------


def test_champions_by_dimension_picks_lowest_wape_model():
    dimension_result = {
        "seg1": {
            "naive": {"n": 10, "wape": 0.5},
            "seasonal_naive": {"n": 10, "wape": 0.3},
        },
    }
    champions = champions_by_dimension(dimension_result)
    assert champions["seg1"] == {"model": "seasonal_naive", "wape": 0.3}


def test_champions_by_dimension_ignores_segments_below_min_n():
    dimension_result = {
        "tiny": {
            "naive": {"n": MIN_SEGMENT_SCORED_N - 1, "wape": 0.1},
        },
    }
    champions = champions_by_dimension(dimension_result)
    assert champions["tiny"] == {"model": None, "wape": None}


# --- accuracy_trend_by_model ---------------------------------------------------


def test_accuracy_trend_by_model_detects_deteriorating_direction():
    by_as_of_date = {
        "2013-01-01": {"naive": {"wape": 0.5}},
        "2013-01-08": {"naive": {"wape": 0.7}},
        "2013-01-15": {"naive": {"wape": 0.9}},
    }
    trend = accuracy_trend_by_model(by_as_of_date)
    assert trend["naive"]["direction"] == "deteriorating"
    assert trend["naive"]["wape_ols_slope_per_as_of_step"] == pytest.approx(0.2)
    assert trend["naive"]["points_used"] == 3


def test_accuracy_trend_by_model_detects_improving_direction():
    by_as_of_date = {
        "2013-01-01": {"naive": {"wape": 0.9}},
        "2013-01-08": {"naive": {"wape": 0.5}},
    }
    trend = accuracy_trend_by_model(by_as_of_date)
    assert trend["naive"]["direction"] == "improving"


def test_accuracy_trend_by_model_reports_insufficient_data_for_one_point():
    by_as_of_date = {"2013-01-01": {"naive": {"wape": 0.5}}}
    trend = accuracy_trend_by_model(by_as_of_date)
    assert trend["naive"]["direction"] == "insufficient_data"
    assert trend["naive"]["wape_ols_slope_per_as_of_step"] is None


# --- identify_findings ---------------------------------------------------------


def _by_model_metrics(n, wape, bias=0.0):
    return {"n": n, "wape": wape, "forecast_bias": bias}


def test_identify_findings_returns_empty_list_when_no_champion():
    findings = identify_findings({"by_dimension": {}}, {}, champion_model=None)
    assert findings == []


def test_identify_findings_flags_a_weak_segment():
    overall_by_model = {"naive": _by_model_metrics(100, 0.5)}
    by_dimension = {
        "item_family": {
            "WEAK": {"naive": _by_model_metrics(10, 1.0)},   # 2x overall -> flagged
            "FINE": {"naive": _by_model_metrics(10, 0.5)},   # same as overall -> not flagged
        },
    }
    findings = identify_findings({"by_dimension": by_dimension}, overall_by_model, champion_model="naive")
    weak = [f for f in findings if f["category"] == "weak_segment"]
    assert len(weak) == 1
    assert weak[0]["segment"] == "WEAK"
    assert weak[0]["ratio_to_overall"] == pytest.approx(2.0)


def test_identify_findings_flags_systematic_bias():
    overall_by_model = {"naive": _by_model_metrics(100, 0.5, bias=0.0)}
    by_dimension = {
        "item_family": {
            "OVER": {"naive": _by_model_metrics(10, 0.5, bias=0.30)},
            "FINE": {"naive": _by_model_metrics(10, 0.5, bias=0.05)},
        },
    }
    findings = identify_findings({"by_dimension": by_dimension}, overall_by_model, champion_model="naive")
    bias_findings = [f for f in findings if f["category"] == "systematic_bias"]
    assert len(bias_findings) == 1
    assert bias_findings[0]["segment"] == "OVER"
    assert "over-forecasts" in bias_findings[0]["statement"]


def test_identify_findings_flags_a_segment_champion_switch():
    overall_by_model = {"naive": _by_model_metrics(100, 0.5)}
    by_dimension = {
        "item_family": {
            "SWITCH": {
                "naive": _by_model_metrics(10, 1.0),
                "seasonal_naive": _by_model_metrics(10, 0.3),  # clearly better here
            },
        },
    }
    findings = identify_findings({"by_dimension": by_dimension}, overall_by_model, champion_model="naive")
    switches = [f for f in findings if f["category"] == "segment_champion_switch"]
    assert len(switches) == 1
    assert switches[0]["recommended_model"] == "seasonal_naive"
    assert switches[0]["overall_champion_model"] == "naive"


def test_identify_findings_ignores_segments_below_min_n():
    overall_by_model = {"naive": _by_model_metrics(100, 0.5)}
    by_dimension = {
        "item_family": {
            "TINY": {"naive": _by_model_metrics(MIN_SEGMENT_SCORED_N - 1, 5.0, bias=0.9)},
        },
    }
    findings = identify_findings({"by_dimension": by_dimension}, overall_by_model, champion_model="naive")
    assert findings == []
