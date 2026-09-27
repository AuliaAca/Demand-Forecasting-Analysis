"""Run the whole pipeline built so far, end-to-end, against the synthetic fixture.

This is NOT a substitute for a real run against the actual Favorita data —
it proves the pipeline's *plumbing* composes correctly, using data this
repository controls and ships in tests/fixtures/. It writes its output under
reports/fixture_smoke_test/ (git-ignored), never to docs/dataset_card.md or
docs/data_quality/dq_report.md, so it can never be mistaken for real output.

Covers, as of Phase 14 (Phases 12-13, Airflow and BigQuery, have their own
separate, non-DuckDB validation paths -- see docs/phase_reports/phase12.md
and phase13.md -- and are not part of this fixture pipeline):
    acquire -> convert -> profile -> select dev scope -> render dataset card
    -> run DQ rules -> render DQ report -> build the SQL warehouse
    (staging -> intermediate -> marts) -> reconciliation checks -> run the
    exploratory demand analysis -> render the EDA findings report -> run
    the rolling-origin backtest (Naive vs. Seasonal Naive) -> render the
    forecast baselines report -> run the statistical-models backtest
    (SES, Croston, SBA) -> render the statistical models report -> run the
    ML backtest (leakage-safe features, LightGBM) -> render the ML report
    -> run the Phase 08 forecast evaluation (segment/horizon/time
    breakdowns, actionable findings) -> render the forecast evaluation
    report -> run the Phase 09 root-cause analysis (data issues, forecast
    discrepancies) -> render the root cause analysis report -> run the
    Phase 10 monitoring check (forecast accuracy, forecast deterioration,
    data quality, anomalies) -> render the monitoring report -> run the
    Phase 11 alerts + discrepancy tracker check (persisted monitoring
    history, status-transition alerts, an idempotent tracker) -> render
    the alerts & tracker report -> render the Phase 14 decision-oriented
    dashboard (demand, accuracy, discrepancies/anomalies, monitoring,
    alerts/trackers, actionable findings, all in one page)

Usage:
    python scripts/run_fixture_smoke_test.py
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import os  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "reports" / "fixture_smoke_test"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "favorita_sample"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    data_dir = OUTPUT_DIR / "data"
    os.environ["DEMANDFLOW_DATA_DIR"] = str(data_dir)

    # Import after setting the env var, so config.load_config() picks it up.
    from demandflow.config import load_config
    from demandflow.ingest.acquire_favorita import (
        _copy_fixture_as_raw,
        build_manifest,
        write_manifest,
    )
    from demandflow.ingest.convert_to_parquet import convert_all
    from demandflow.profiling.profile_favorita import profile, write_report
    from demandflow.quality.rules import findings_to_dicts, run_all_rules
    from demandflow.reporting.generate_dataset_card import generate_and_write as generate_dataset_card
    from demandflow.reporting.generate_dq_report import generate_and_write as generate_dq_report
    from demandflow.scope.select_dev_scope import (
        compute_item_stats,
        stratify_and_sample,
        summarize_selection,
        write_dev_scope_csv,
    )
    import duckdb
    import json

    cfg = load_config()
    print(f"[1/26] Data dir for this smoke test: {cfg.paths.data_dir}")

    print("[2/26] 'Acquiring' data (copying the fixture in place of a real Kaggle download)")
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    manifest = build_manifest(cfg.paths.raw_dir, cfg.dataset.kaggle_competition_slug)
    write_manifest(manifest, cfg.paths.raw_dir)
    print(f"       {len(manifest.files)} files checksummed")

    print("[3/26] Converting CSV -> Parquet")
    counts = convert_all(cfg)
    print(f"       {counts}")

    print("[4/26] Profiling")
    report = profile(cfg)
    profile_path = OUTPUT_DIR / "profile_summary.json"
    write_report(report, profile_path)
    print(f"       wrote {profile_path}")

    print("[5/26] Selecting the controlled development scope")
    con = duckdb.connect()
    stats = compute_item_stats(
        con, cfg.paths.parquet_dir / "train.parquet", cfg.paths.parquet_dir / "items.parquet", cfg.dev_scope
    )
    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    summary = summarize_selection(selection)
    dev_scope_csv_path = OUTPUT_DIR / "dev_scope_items.csv"
    write_dev_scope_csv(selection, dev_scope_csv_path)
    summary_path = OUTPUT_DIR / "dev_scope_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    con.close()
    print(f"       selected {summary['selected_items']}/{summary['total_items']} items -> {dev_scope_csv_path}")

    print("[6/26] Rendering the dataset card (fixture preview — NOT the real dataset card)")
    card_path = OUTPUT_DIR / "dataset_card_PREVIEW.md"
    generate_dataset_card(
        profile_path=profile_path,
        dev_scope_summary_path=summary_path,
        out_path=card_path,
        dataset_display_name=cfg.dataset.display_name,
        kaggle_competition_slug=cfg.dataset.kaggle_competition_slug,
    )
    print(f"       wrote {card_path}")

    print("[7/26] Running the Phase 02 data-quality rule catalog")
    con = duckdb.connect()
    available_tables = [p.stem for p in cfg.paths.parquet_dir.glob("*.parquet")]
    findings = run_all_rules(
        con,
        cfg.paths.parquet_dir / "train.parquet",
        cfg.paths.parquet_dir / "stores.parquet",
        cfg.paths.parquet_dir / "items.parquet",
        available_tables=available_tables,
    )
    con.close()
    findings_path = OUTPUT_DIR / "dq_findings.json"
    findings_path.write_text(json.dumps(findings_to_dicts(findings), indent=2), encoding="utf-8")
    severities = ", ".join(f"{f.rule_id}={f.severity}" for f in findings)
    print(f"       {severities}")

    print("[8/26] Rendering the DQ report (fixture preview — NOT the real DQ report)")
    dq_report_path = OUTPUT_DIR / "dq_report_PREVIEW.md"
    generate_dq_report(findings_path, dq_report_path, cfg.dataset.display_name)
    print(f"       wrote {dq_report_path}")

    print("[9/26] Building the SQL warehouse (staging -> intermediate -> marts) and reconciling")
    from demandflow.transform.build_warehouse import build_warehouse

    warehouse_db_path = OUTPUT_DIR / "warehouse.duckdb"
    warehouse_con, checks = build_warehouse(
        cfg, db_path=warehouse_db_path, dev_scope_csv_path=dev_scope_csv_path
    )
    warehouse_con.close()
    for c in checks:
        print(f"       [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    failed = [c for c in checks if not c.passed]

    print("[10/26] Running the Phase 04 exploratory demand analysis")
    from demandflow.analysis.run_eda import run_and_write

    eda_result = run_and_write(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase04")
    print(f"       wrote {eda_result['summary_path']} and {len(eda_result['chart_paths'])} chart(s)")

    print("[11/26] Rendering the EDA findings report (fixture preview — NOT the real findings)")
    from demandflow.reporting.generate_eda_report import generate_and_write as generate_eda_report

    eda_report_path = OUTPUT_DIR / "eda_findings_PREVIEW.md"
    eda_chart_paths = {name: str(path) for name, path in eda_result["chart_paths"].items()}
    generate_eda_report(eda_result["summary_path"], eda_report_path, cfg.dataset.display_name, eda_chart_paths)
    print(f"       wrote {eda_report_path}")

    print("[12/26] Running the Phase 05 rolling-origin backtest (Naive vs. Seasonal Naive)")
    from demandflow.forecasting.run_backtest import run_and_write as run_backtest

    backtest_result = run_backtest(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase05")
    bt_summary = backtest_result["summary"]
    print(
        f"       {bt_summary['total_scored_records']}/{bt_summary['total_records']} scored; "
        f"lower-WAPE model: {bt_summary['lower_wape_model']}"
    )

    print("[13/26] Rendering the forecast baselines report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_forecast_baselines_report import (
        generate_and_write as generate_backtest_report,
    )

    backtest_report_path = OUTPUT_DIR / "forecast_baselines_PREVIEW.md"
    generate_backtest_report(
        backtest_result["summary_path"], backtest_report_path, cfg.dataset.display_name,
        cfg.forecasting.horizon_days, cfg.forecasting.season_length_days, cfg.forecasting.as_of_cadence_days,
    )
    print(f"       wrote {backtest_report_path}")

    print("[14/26] Running the Phase 06 statistical-models backtest (SES, Croston, SBA)")
    from demandflow.forecasting.run_statistical_backtest import run_and_write as run_statistical_backtest

    stat_result = run_statistical_backtest(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase06")
    stat_summary = stat_result["summary"]
    print(
        f"       {stat_summary['total_scored_records']}/{stat_summary['total_records']} scored; "
        f"lower-WAPE model overall: {stat_summary['lower_wape_model']}"
    )

    print("[15/26] Rendering the statistical models report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_statistical_models_report import (
        generate_and_write as generate_statistical_report,
    )

    statistical_report_path = OUTPUT_DIR / "statistical_models_PREVIEW.md"
    generate_statistical_report(
        stat_result["summary_path"], statistical_report_path, cfg.dataset.display_name,
        cfg.forecasting.horizon_days, cfg.forecasting.season_length_days,
    )
    print(f"       wrote {statistical_report_path}")

    print("[16/26] Running the Phase 07 ML backtest (LightGBM, leakage-safe features)")
    from demandflow.forecasting.run_ml_backtest import run_and_write as run_ml_backtest

    ml_result = run_ml_backtest(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase07")
    ml_summary = ml_result["summary"]
    print(
        f"       model_trained={ml_summary['model_trained']}, "
        f"{ml_summary['holdout_scored_rows']} scorable holdout rows; "
        f"lower-WAPE model: {ml_summary['lower_wape_model']}"
    )

    print("[17/26] Rendering the ML forecasting report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_ml_report import generate_and_write as generate_ml_report

    ml_report_path = OUTPUT_DIR / "ml_forecasting_PREVIEW.md"
    generate_ml_report(ml_result["summary_path"], ml_report_path, cfg.dataset.display_name, cfg.forecasting.horizon_days)
    print(f"       wrote {ml_report_path}")

    print("[18/26] Running the Phase 08 forecast evaluation (segments, horizon, time, findings)")
    from demandflow.evaluation.run_evaluation import run_and_write as run_evaluation

    eval_result = run_evaluation(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase08")
    eval_summary = eval_result["summary"]
    print(
        f"       champion model: {eval_summary['champion_model']}; "
        f"{len(eval_summary['findings'])} finding(s)"
    )

    print("[19/26] Rendering the forecast evaluation report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_evaluation_report import generate_and_write as generate_evaluation_report

    evaluation_report_path = OUTPUT_DIR / "forecast_evaluation_PREVIEW.md"
    generate_evaluation_report(
        eval_result["summary_path"], evaluation_report_path, cfg.dataset.display_name, cfg.forecasting.horizon_days
    )
    print(f"       wrote {evaluation_report_path}")

    print("[20/26] Running the Phase 09 root-cause analysis (data issues + forecast discrepancies)")
    from demandflow.rca.run_rca import run_and_write as run_rca

    rca_result = run_rca(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase09")
    rca_summary = rca_result["summary"]
    print(
        f"       {len(rca_summary['data_issue_rca'])} data-issue record(s); "
        f"{rca_summary['forecast_discrepancy_triggers_investigated']} forecast-discrepancy trigger(s) investigated"
    )

    print("[21/26] Rendering the root cause analysis report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_rca_report import generate_and_write as generate_rca_report

    rca_report_path = OUTPUT_DIR / "root_cause_analysis_PREVIEW.md"
    generate_rca_report(rca_result["summary_path"], rca_report_path, cfg.dataset.display_name)
    print(f"       wrote {rca_report_path}")

    print("[22/26] Running the Phase 10 monitoring check (accuracy, deterioration, DQ, anomalies)")
    from demandflow.monitoring.run_monitoring import run_and_write as run_monitoring

    monitoring_result = run_monitoring(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase10")
    monitoring_summary = monitoring_result["summary"]
    signal_bits = ", ".join(f"{s['signal']}={s['status']}" for s in monitoring_summary["signals"])
    print(f"       overall status: {monitoring_summary['overall_status']} ({signal_bits})")

    print("[23/26] Rendering the monitoring report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_monitoring_report import generate_and_write as generate_monitoring_report

    monitoring_report_path = OUTPUT_DIR / "monitoring_PREVIEW.md"
    generate_monitoring_report(monitoring_result["summary_path"], monitoring_report_path, cfg.dataset.display_name)
    print(f"       wrote {monitoring_report_path}")

    print("[24/26] Running the Phase 11 alerts + discrepancy tracker check")
    from demandflow.alerts.run_alerts import run_and_write as run_alerts

    alerts_result = run_alerts(cfg, db_path=warehouse_db_path, out_dir=OUTPUT_DIR / "phase11")
    alerts_summary = alerts_result["summary"]
    print(
        f"       run #{alerts_summary['run_seq']}: {len(alerts_summary['alerts'])} alert(s), "
        f"{len(alerts_summary['open_tracker_items'])} open tracker item(s)"
    )

    print("[25/26] Rendering the alerts & tracker report (fixture preview — NOT the real report)")
    from demandflow.reporting.generate_alerts_report import generate_and_write as generate_alerts_report

    alerts_report_path = OUTPUT_DIR / "alerts_and_tracker_PREVIEW.md"
    generate_alerts_report(alerts_result["summary_path"], alerts_report_path, cfg.dataset.display_name)
    print(f"       wrote {alerts_report_path}")

    print("[26/26] Rendering the decision-oriented dashboard (fixture preview — NOT the real dashboard)")
    from demandflow.reporting.generate_dashboard import generate_and_write as generate_dashboard

    dashboard_path = OUTPUT_DIR / "dashboard_PREVIEW.html"
    generate_dashboard(OUTPUT_DIR, dashboard_path, cfg.dataset.display_name)
    print(f"       wrote {dashboard_path}")

    print("\nSmoke test complete. All outputs are under:", OUTPUT_DIR)
    if failed:
        raise SystemExit(f"{len(failed)} reconciliation check(s) failed: {[c.name for c in failed]}")


if __name__ == "__main__":
    main()
