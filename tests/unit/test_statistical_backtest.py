"""Tests for the Phase 06 statistical-models backtest, against the fixture.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the backtest (see docs/phase_reports/phase06.md), not
just asserting "it runs without error" -- including the honest result that
Croston/SBA do NOT outperform the baselines on this tiny fixture, and why.
"""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.backtest import summarize_by_segment
from demandflow.forecasting.run_statistical_backtest import (
    build_extended_models,
    load_intermittency_classes,
    run_and_write,
)
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


def test_build_extended_models_has_all_five():
    models = build_extended_models(season_length=7)
    assert set(models) == {"naive", "seasonal_naive", "ses", "croston", "sba"}


def test_load_intermittency_classes_covers_every_item(built_warehouse):
    cfg, db_path, _ = built_warehouse
    con = duckdb.connect(str(db_path))
    classes = load_intermittency_classes(con)
    con.close()
    assert set(classes) == {100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 999}
    assert set(classes.values()) <= {"smooth", "intermittent", "erratic", "lumpy", "insufficient_data"}


def test_run_and_write_produces_five_models_and_loads_fct_forecast(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase06")
    summary = result["summary"]

    assert set(summary["overall_by_model"]) == {"naive", "seasonal_naive", "ses", "croston", "sba"}

    con = duckdb.connect(str(db_path))
    models_in_table = {r[0] for r in con.execute("SELECT DISTINCT model FROM fct_forecast").fetchall()}
    con.close()
    assert models_in_table == {"naive", "seasonal_naive", "ses", "croston", "sba"}


def test_overall_comparison_matches_hand_verified_wape(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase06")
    overall = result["summary"]["overall_by_model"]

    assert overall["naive"]["wape"] == pytest.approx(1.0733590733590734)
    assert overall["seasonal_naive"]["wape"] == pytest.approx(0.9078947368421053)
    assert overall["ses"]["wape"] == pytest.approx(1.2039383044934178)
    assert overall["croston"]["wape"] == pytest.approx(1.4528090525550303)
    assert overall["sba"]["wape"] == pytest.approx(1.42051609027477)
    # Honest result: on this fixture, Seasonal Naive has the lowest WAPE of
    # all five models -- the Croston family does NOT win here (see
    # docs/phase_reports/phase06.md for why that's not surprising at this
    # sample size, and why it doesn't invalidate trying it).
    assert result["summary"]["lower_wape_model"] == "seasonal_naive"


def test_by_intermittency_class_matches_hand_verified_wape(built_warehouse):
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase06")
    by_segment = result["summary"]["by_intermittency_class"]

    assert set(by_segment) == {"intermittent", "lumpy", "smooth"}

    intermittent = by_segment["intermittent"]
    assert intermittent["naive"]["wape"] == pytest.approx(1.1979166666666667)
    assert intermittent["seasonal_naive"]["wape"] == pytest.approx(0.8472222222222222)
    assert intermittent["croston"]["wape"] == pytest.approx(2.1028910897057593)
    assert intermittent["sba"]["wape"] == pytest.approx(2.021704868553806)
    # Croston/SBA are WORSE than both baselines on the very segment they
    # target, on this fixture -- the honest empirical result.
    assert intermittent["croston"]["wape"] > intermittent["naive"]["wape"]
    assert intermittent["sba"]["wape"] > intermittent["naive"]["wape"]

    lumpy = by_segment["lumpy"]
    assert lumpy["naive"]["wape"] == pytest.approx(1.0)
    assert lumpy["seasonal_naive"]["wape"] == pytest.approx(0.9625)


def test_smooth_segment_has_no_scored_records_on_this_fixture(built_warehouse):
    """items 109 and 999 (Phase 04's "smooth" class) each sold only 1-3
    times total, spread across DIFFERENT stores -- so every (store, item)
    series for them has an active window of exactly one day, leaving no
    room for any horizon step to fall inside it. Not a bug: a real
    consequence of how short this fixture's history is."""
    cfg, db_path, tmp_path = built_warehouse
    result = run_and_write(cfg, db_path=db_path, out_dir=tmp_path / "phase06")
    smooth = result["summary"]["by_intermittency_class"].get("smooth")
    if smooth is not None:  # summarize_by_segment omits empty segments
        for metrics in smooth.values():
            assert metrics["n"] == 0


def test_summarize_by_segment_groups_unlabeled_items_as_unclassified():
    from demandflow.forecasting.backtest import ForecastRecord

    records = [
        ForecastRecord("2013-01-01", 1, "2013-01-02", 1, 100, "naive", 5.0, 4.0, True),
        ForecastRecord("2013-01-01", 1, "2013-01-02", 1, 200, "naive", 3.0, 3.0, True),
    ]
    result = summarize_by_segment(records, item_to_segment={100: "smooth"})
    assert set(result) == {"smooth", "unclassified"}
    assert result["smooth"]["naive"]["n"] == 1
    assert result["unclassified"]["naive"]["n"] == 1
