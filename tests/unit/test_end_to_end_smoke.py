"""Phase 15 end-to-end smoke test.

Every previous phase's own test file already rebuilds a throwaway warehouse
from tests/fixtures/favorita_sample/ and asserts detailed, hand-verified
numbers for that one phase -- but always in isolation. Nothing chains every
phase's real entrypoint together on one shared warehouse in one continuous
run, which is exactly the gap docs/00_requirement_analysis_and_system_plan.md
named for this phase: "Phase 15: testing and reliability (CI, idempotent
runs, end-to-end smoke test on fixtures)".

This file does not re-assert business numbers -- those are already pinned,
phase by phase, elsewhere. It proves two things instead:

1. The pipeline is actually wired together: ingest -> warehouse -> EDA ->
   three backtest variants -> evaluation -> RCA -> monitoring -> alerts,
   each phase's real `run_and_write()`, run in sequence, each producing its
   real output file, on one warehouse.
2. Idempotency (CLAUDE.md Section 14): rebuilding the warehouse a second
   time from the same fixture, and re-running evaluation against it,
   reproduces the exact same numbers -- rerunning the pipeline must not
   silently drift or accumulate.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from demandflow.alerts.run_alerts import run_and_write as run_alerts
from demandflow.analysis.run_eda import run_and_write as run_eda
from demandflow.config import load_config
from demandflow.evaluation.run_evaluation import run_and_write as run_evaluation
from demandflow.forecasting.run_backtest import run_and_write as run_backtest
from demandflow.forecasting.run_ml_backtest import run_and_write as run_ml_backtest
from demandflow.forecasting.run_statistical_backtest import run_and_write as run_statistical_backtest
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.monitoring.run_monitoring import run_and_write as run_monitoring
from demandflow.rca.run_rca import run_and_write as run_rca
from demandflow.scope.select_dev_scope import compute_item_stats, stratify_and_sample, write_dev_scope_csv
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


def _build_warehouse(tmp_path: Path, cfg, db_path: Path, suffix: str) -> None:
    """Ingest the fixture and (re)build the warehouse at db_path -- the same
    steps `make ingest && make warehouse` runs, factored out so the
    idempotency test below can call it twice."""
    con = duckdb.connect()
    stats = compute_item_stats(
        con, cfg.paths.parquet_dir / "train.parquet", cfg.paths.parquet_dir / "items.parquet", cfg.dev_scope
    )
    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    con.close()
    dev_scope_csv = tmp_path / f"dev_scope_items_{suffix}.csv"
    write_dev_scope_csv(selection, dev_scope_csv)

    warehouse_con, checks = build_warehouse(cfg, db_path=db_path, dev_scope_csv_path=dev_scope_csv)
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
    warehouse_con.close()


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    convert_all(cfg)

    db_path = tmp_path / "warehouse.duckdb"
    _build_warehouse(tmp_path, cfg, db_path, suffix="a")
    return cfg, db_path, tmp_path


def test_full_pipeline_runs_end_to_end_on_the_fixture(pipeline):
    cfg, db_path, tmp_path = pipeline
    out_root = tmp_path / "reports"

    eda_result = run_eda(cfg, db_path=db_path, out_dir=out_root / "phase04")
    assert eda_result["summary_path"].exists()

    backtest_result = run_backtest(cfg, db_path=db_path, out_dir=out_root / "phase05")
    assert backtest_result["summary_path"].exists()
    assert backtest_result["summary"]["lower_wape_model"] is not None

    stat_result = run_statistical_backtest(cfg, db_path=db_path, out_dir=out_root / "phase06")
    assert stat_result["summary_path"].exists()
    assert stat_result["summary"]["lower_wape_model"] is not None

    ml_result = run_ml_backtest(cfg, db_path=db_path, out_dir=out_root / "phase07")
    assert ml_result["summary_path"].exists()
    assert ml_result["summary"]["model_trained"] is True

    eval_result = run_evaluation(cfg, db_path=db_path, out_dir=out_root / "phase08")
    assert eval_result["summary_path"].exists()
    assert eval_result["summary"]["champion_model"] is not None
    assert len(eval_result["summary"]["by_dimension"]) > 0

    rca_result = run_rca(cfg, db_path=db_path, out_dir=out_root / "phase09")
    assert rca_result["summary_path"].exists()
    assert len(rca_result["summary"]["data_issue_rca"]) > 0

    monitoring_result = run_monitoring(cfg, db_path=db_path, out_dir=out_root / "phase10")
    assert monitoring_result["summary_path"].exists()
    assert len(monitoring_result["summary"]["signals"]) == 4

    alerts_result = run_alerts(cfg, db_path=db_path, out_dir=out_root / "phase11")
    assert alerts_result["summary_path"].exists()
    assert alerts_result["summary"]["overall_status"] in {"OK", "WARN", "BREACH"}


def test_a_second_alerts_run_advances_run_seq_without_erroring(pipeline):
    # The alerts/monitoring-history tables are the one deliberate exception
    # to "rebuild, don't accumulate" -- record_snapshot() APPENDS a row per
    # run by design (demandflow.alerts.history), so re-running Phase 11
    # against the same warehouse must succeed and advance run_seq, not
    # error or silently overwrite the previous run's history.
    cfg, db_path, tmp_path = pipeline
    first = run_alerts(cfg, db_path=db_path, out_dir=tmp_path / "reports" / "phase11_run1")
    second = run_alerts(cfg, db_path=db_path, out_dir=tmp_path / "reports" / "phase11_run2")
    assert second["summary"]["run_seq"] == first["summary"]["run_seq"] + 1


def test_rebuilding_the_warehouse_is_idempotent(pipeline):
    cfg, db_path, tmp_path = pipeline
    first = run_evaluation(cfg, db_path=db_path, out_dir=tmp_path / "reports" / "phase08_before_rebuild")

    with duckdb.connect(str(db_path)) as con:
        (row_count_before,) = con.execute("SELECT COUNT(*) FROM fct_sales_daily").fetchone()

    # Rebuild from scratch -- the same fixture, a fresh dev-scope sample
    # with the same seed, into the same db_path -- simulating a rerun of
    # `make ingest && make warehouse`.
    _build_warehouse(tmp_path, cfg, db_path, suffix="b")

    with duckdb.connect(str(db_path)) as con:
        (row_count_after,) = con.execute("SELECT COUNT(*) FROM fct_sales_daily").fetchone()
    assert row_count_after == row_count_before

    second = run_evaluation(cfg, db_path=db_path, out_dir=tmp_path / "reports" / "phase08_after_rebuild")
    assert second["summary"]["champion_model"] == first["summary"]["champion_model"]
    assert second["summary"]["overall_by_model"] == first["summary"]["overall_by_model"]
