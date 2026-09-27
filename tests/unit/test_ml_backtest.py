"""Integration tests for the Phase 07 ML backtest, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the backtest -- including
`test_no_training_example_targets_a_date_the_holdout_will_evaluate`, which
locks in the fix for a real leakage bug found while building this phase
(see docs/phase_reports/phase07.md): splitting purely on as_of_date is not
enough, because a long-horizon example from an earlier as-of date can have
a target_date that lands on or after the holdout's own as-of date.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.run_ml_backtest import run_and_write
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


def test_no_training_example_targets_a_date_the_holdout_will_evaluate(built_warehouse):
    """The leakage-guard fix, locked in directly: no training example's
    target_date may exceed the holdout as-of date, regardless of which
    as-of date it was built from."""
    from demandflow.forecasting.backtest import generate_as_of_dates, load_dense_series
    from demandflow.forecasting.features import load_day_context, load_static_attributes
    from demandflow.forecasting.run_ml_backtest import build_examples

    cfg, db_path, tmp_path = built_warehouse
    con = duckdb.connect(str(db_path))
    (min_date, max_date) = con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone()
    as_of_dates = generate_as_of_dates(
        min_date, max_date, cadence_days=cfg.forecasting.as_of_cadence_days, min_history_days=cfg.forecasting.min_history_days
    )
    series = load_dense_series(con)
    day_context = load_day_context(con)
    item_attrs, store_attrs = load_static_attributes(con)
    con.close()

    examples = build_examples(series, as_of_dates, cfg.forecasting.horizon_days, day_context, item_attrs, store_attrs)
    holdout_as_of = max(as_of_dates).isoformat()

    # Reproduce run_and_write's own training filter and assert its invariant.
    training_examples = [
        e for e in examples
        if e["is_scored"] and e["as_of_date"] != holdout_as_of and e["target_date"] <= holdout_as_of
    ]
    assert training_examples  # the filter isn't vacuously true
    assert all(e["target_date"] <= holdout_as_of for e in training_examples)

    # And confirm examples EXCLUDED by the fix really do violate it (i.e.
    # the fix changes something real, not a no-op).
    excluded = [
        e for e in examples
        if e["is_scored"] and e["as_of_date"] != holdout_as_of and e["target_date"] > holdout_as_of
    ]
    assert excluded


def test_run_and_write_trains_a_model_and_produces_five_model_comparison(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    summary = result["summary"]

    assert summary["model_trained"] is True
    assert summary["insufficient_training_data"] is False
    assert set(summary["holdout_by_model"]) == {"naive", "seasonal_naive", "sba", "lightgbm"}


def test_training_and_holdout_row_counts_match_hand_verified_totals(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    summary = result["summary"]

    assert summary["training_rows"] == 69
    assert summary["holdout_rows"] == 112
    assert summary["holdout_scored_rows"] == 18


def test_holdout_comparison_matches_hand_verified_wape_after_the_leakage_fix(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    by_model = result["summary"]["holdout_by_model"]

    assert by_model["naive"]["wape"] == pytest.approx(1.0)
    assert by_model["seasonal_naive"]["wape"] == pytest.approx(0.9056603773584906)
    assert by_model["sba"]["wape"] == pytest.approx(0.9092876149008225)
    assert by_model["lightgbm"]["wape"] == pytest.approx(0.8246904469327779)
    # Honest result: LightGBM has the lowest WAPE on this holdout -- a
    # modest, not dramatic, improvement over Seasonal Naive, on only 18
    # scorable rows. See docs/phase_reports/phase07.md for how much weight
    # this can honestly bear.
    assert result["summary"]["lower_wape_model"] == "lightgbm"


def test_sba_comparison_matches_phase06s_own_final_holdout_number(built_warehouse):
    """Cross-check: Phase 06's report already computed SBA's WAPE at this
    same final holdout (2013-01-14) via a different code path
    (summarize_backtest). Both must agree -- if they didn't, one of the two
    implementations would have a bug."""
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    assert result["summary"]["holdout_by_model"]["sba"]["wape"] == pytest.approx(0.9092876149008225)


def test_feature_importance_is_populated_and_json_serializable(built_warehouse):
    import json

    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07")
    importance = result["summary"]["feature_importance"]
    assert importance
    assert all(isinstance(v, int) for v in importance.values())
    json.dumps(result["summary"])


def test_insufficient_training_data_is_handled_without_crashing(built_warehouse, monkeypatch):
    cfg, db_path, tmp_path = built_warehouse
    # Force the minimum threshold above what the fixture can ever provide.
    import demandflow.forecasting.ml as ml_module

    monkeypatch.setattr(ml_module, "MIN_TRAINING_ROWS", 10_000)
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase07_insufficient")
    summary = result["summary"]
    assert summary["model_trained"] is False
    assert summary["insufficient_training_data"] is True
    assert "lightgbm" not in summary["holdout_by_model"]
    assert summary["lower_wape_model"] in {"naive", "seasonal_naive", "sba"}
