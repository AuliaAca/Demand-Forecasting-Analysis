"""End-to-end test of the Phase 03 layered SQL warehouse, against the fixture.

Builds the whole chain (acquire -> convert -> select dev scope -> build
warehouse) in a tmp_path sandbox, then asserts against hand-counted facts
about tests/fixtures/favorita_sample/ -- the same fixture Phase 01/02 use,
now carried one layer further into staging/intermediate/marts.
"""

import shutil
from pathlib import Path

import duckdb
import pytest

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
def warehouse(tmp_path, monkeypatch):
    """Builds a full warehouse from the fixture and yields the open connection.

    dev_scope_items.csv is written under tmp_path, never under the repo's
    real configs/ directory (build_warehouse's dev_scope_csv_path parameter
    exists specifically so tests don't have to touch real repo paths).
    """
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
    yield warehouse_con, checks
    warehouse_con.close()


def test_all_reconciliation_checks_pass(warehouse):
    con, checks = warehouse
    failed = [c for c in checks if not c.passed]
    assert not failed, f"Failed checks: {[(c.name, c.detail) for c in failed]}"
    assert len(checks) == 7


def test_stg_sales_row_count_after_dedup(warehouse):
    con, _ = warehouse
    # 52 raw rows, one duplicate group of 2 collapses to 1 -> 51 staged rows.
    (n,) = con.execute("SELECT COUNT(*) FROM stg_sales").fetchone()
    assert n == 51


def test_stg_sales_keeps_highest_id_on_duplicate(warehouse):
    con, _ = warehouse
    row = con.execute(
        "SELECT id, was_duplicate_key, was_conflicting_duplicate FROM stg_sales "
        "WHERE date = '2013-01-02' AND store_nbr = 1 AND item_nbr = 100"
    ).fetchone()
    assert row == (6, True, False)  # id 6 > id 5; values agreed, so not conflicting


def test_stg_sales_flags_the_planted_return_and_extreme_value(warehouse):
    con, _ = warehouse
    flagged = dict(
        con.execute(
            "SELECT id, is_return OR is_extreme_value FROM stg_sales WHERE is_return OR is_extreme_value"
        ).fetchall()
    )
    assert flagged == {16: True, 52: True}


def test_stg_sales_rejected_null_keys_is_empty_on_this_fixture(warehouse):
    con, _ = warehouse
    (n,) = con.execute("SELECT COUNT(*) FROM stg_sales_rejected_null_keys").fetchone()
    assert n == 0


def test_orphan_item_row_kept_and_flagged_despite_dev_scope_filter(warehouse):
    con, _ = warehouse
    row = con.execute(
        "SELECT item_nbr, has_unknown_item FROM stg_sales WHERE item_nbr = 999"
    ).fetchone()
    assert row == (999, True)


def test_dense_grid_matches_hand_counted_active_window(warehouse):
    """store_nbr=1, item_nbr=100: 13 real observations (post-dedup) spanning
    2013-01-01..2013-01-20, so a 20-day dense window with 7 imputed days at
    exactly {03, 06, 08, 10, 12, 14, 17} (hand-counted from the fixture)."""
    con, _ = warehouse
    rows = con.execute(
        "SELECT date, unit_sales, is_imputed_zero FROM fct_sales_daily "
        "WHERE store_nbr = 1 AND item_nbr = 100 ORDER BY date"
    ).fetchall()
    assert len(rows) == 20
    imputed_days = {r[0].day for r in rows if r[2]}
    assert imputed_days == {3, 6, 8, 10, 12, 14, 17}
    for date, unit_sales, is_imputed in rows:
        if is_imputed:
            assert unit_sales == 0.0


def test_calendar_holiday_resolution_by_locale(warehouse):
    con, _ = warehouse
    # National holiday (2013-01-01): every store.
    national = con.execute(
        "SELECT COUNT(*) FROM int_calendar_by_store WHERE date = '2013-01-01' AND is_holiday"
    ).fetchone()[0]
    assert national == 5

    # Local holiday in Quito (2013-01-06): only stores 1 and 2 (city=Quito).
    local_rows = con.execute(
        "SELECT store_nbr, is_holiday FROM int_calendar_by_store WHERE date = '2013-01-06' ORDER BY store_nbr"
    ).fetchall()
    assert local_rows == [(1, True), (2, True), (3, False), (4, False), (5, False)]

    # National "Bridge" holiday, transferred=True (2013-01-12): every store,
    # with the transferred flag passed through (not further resolved).
    bridge_rows = con.execute(
        "SELECT DISTINCT holiday_type, holiday_transferred FROM int_calendar_by_store WHERE date = '2013-01-12'"
    ).fetchall()
    assert bridge_rows == [("Bridge", True)]


def test_calendar_row_count_is_stores_times_days(warehouse):
    con, _ = warehouse
    (n,) = con.execute("SELECT COUNT(*) FROM int_calendar_by_store").fetchone()
    assert n == 5 * 20  # 5 stores x 20 calendar days (2013-01-01..2013-01-20)


def test_dim_hub_and_dim_sku_are_not_scoped_down(warehouse):
    con, _ = warehouse
    hub_n, sku_n = con.execute(
        "SELECT (SELECT COUNT(*) FROM dim_hub), (SELECT COUNT(*) FROM dim_sku)"
    ).fetchone()
    assert hub_n == 5
    assert sku_n == 10  # full catalog, even though only a subset is is_in_dev_scope


def test_fct_dq_result_round_trips_phase02_findings(warehouse):
    con, _ = warehouse
    rows = con.execute("SELECT rule_id, severity FROM fct_dq_result ORDER BY rule_id").fetchall()
    assert dict(rows) == {
        "grain_duplicates": "HIGH",
        "missing_calendar_dates": "MEDIUM",
        "missing_pricing_dimension": "INFO",
        "null_keys": "PASS",
        "onpromotion_missing": "MEDIUM",
        "orphan_dimension_keys": "HIGH",
        "suspicious_extreme_values": "MEDIUM",
        "suspicious_negative_values": "LOW",
    }


def test_build_warehouse_raises_clearly_without_dev_scope_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    convert_all(cfg)

    with pytest.raises(FileNotFoundError, match="dev_scope"):
        build_warehouse(cfg, db_path=tmp_path / "warehouse.duckdb", dev_scope_csv_path=tmp_path / "missing.csv")
