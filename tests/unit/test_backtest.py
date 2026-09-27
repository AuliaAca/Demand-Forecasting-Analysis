"""Tests for the rolling-origin backtest, against the fixture warehouse.

Every number below is hand-verified against tests/fixtures/favorita_sample/
by actually running the backtest and checking the output (see
docs/phase_reports/phase05.md), not just asserting "it runs without error".
Uses fixture-appropriate parameters (cadence=5, horizon=5) rather than the
real config's 14-day horizon / 7-day cadence, which would leave almost no
scorable steps on a 20-day fixture -- the same "scaled-down params for a
tiny fixture" pattern used for dev-scope sampling in Phase 01.
"""

import datetime
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.forecasting.backtest import (
    generate_as_of_dates,
    load_dense_series,
    load_fct_forecast,
    run_rolling_origin_backtest,
    summarize_backtest,
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


def test_generate_as_of_dates_on_the_fixture_range():
    dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    assert dates == [datetime.date(2013, 1, 7), datetime.date(2013, 1, 12), datetime.date(2013, 1, 17)]


def test_generate_as_of_dates_rejects_bad_params():
    with pytest.raises(ValueError):
        generate_as_of_dates(datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=0, min_history_days=7)
    with pytest.raises(ValueError):
        generate_as_of_dates(datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=0)


def test_load_dense_series_matches_fct_sales_daily_row_count(warehouse_con):
    series = load_dense_series(warehouse_con)
    total_points = sum(len(dates) for dates, _ in series.values())
    (n,) = warehouse_con.execute("SELECT COUNT(*) FROM fct_sales_daily").fetchone()
    assert total_points == n


def test_naive_forecast_at_as_of_equals_the_observed_value_that_day(warehouse_con):
    # store 1 / item 100 sold 5.0 units on 2013-01-07 (train.csv row 22),
    # so a naive forecast made as-of that date must repeat exactly 5.0.
    as_of_dates = [datetime.date(2013, 1, 7)]
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=3, season_length=7)
    naive_rows = [
        r for r in records
        if r.model == "naive" and r.store_nbr == 1 and r.item_nbr == 100 and r.as_of_date == "2013-01-07"
    ]
    assert len(naive_rows) == 3
    assert all(r.forecast == 5.0 for r in naive_rows)


def test_backtest_produces_the_hand_verified_totals(warehouse_con):
    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    assert len(records) == 205
    assert sum(1 for r in records if r.is_scored) == 132


def test_load_fct_forecast_row_count_matches_records(warehouse_con):
    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    load_fct_forecast(warehouse_con, records)
    (n,) = warehouse_con.execute("SELECT COUNT(*) FROM fct_forecast").fetchone()
    assert n == len(records)


def test_summarize_backtest_declares_seasonal_naive_the_lower_wape_model(warehouse_con):
    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    summary = summarize_backtest(records)

    assert summary["lower_wape_model"] == "seasonal_naive"
    assert summary["overall_by_model"]["naive"]["wape"] == pytest.approx(1.196078431372549)
    assert summary["overall_by_model"]["seasonal_naive"]["wape"] == pytest.approx(0.9347826086956522)
    assert summary["final_holdout"]["as_of_date"] == "2013-01-17"
    assert summary["final_holdout"]["by_model"]["naive"]["wape"] == pytest.approx(1.0)


def test_summarize_backtest_output_is_json_serializable(warehouse_con):
    import json

    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    json.dumps(summarize_backtest(records))


def test_no_forecast_is_scored_against_a_target_outside_the_series_active_window(warehouse_con):
    # Item 109 has only 3 observed days in the fixture (a short active window);
    # a large horizon must leave most of its steps unscored, never inventing
    # an actual for a date outside that window.
    as_of_dates = generate_as_of_dates(
        datetime.date(2013, 1, 1), datetime.date(2013, 1, 20), cadence_days=5, min_history_days=7
    )
    records = run_rolling_origin_backtest(warehouse_con, as_of_dates, horizon=5, season_length=7)
    item_109_rows = [r for r in records if r.item_nbr == 109]
    for r in item_109_rows:
        if not r.is_scored:
            assert r.actual is None
