"""Phase 10 entrypoint.

Produces one point-in-time monitoring snapshot: reruns Phase 02's DQ rule
catalog against the current parquet files, Phase 04's network-anomaly
screen against the current warehouse, and Phase 06's 5-model rolling-origin
backtest (the same "rebuild, don't trust a stale file" principle Phases
08-09 already established), then classifies each of the four signals with
an explicit PASS/WARN/BREACH threshold (demandflow.monitoring.signals).

Unlike Phase 08/09, this module does not call load_fct_forecast(): the
accuracy and deterioration signals only need the backtest's in-memory
records, and monitoring is a read of the warehouse, not a reason to
persist a new forecast mart to it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from demandflow.analysis.eda import network_anomalies, trend_summary
from demandflow.config import ProjectConfig, load_config
from demandflow.forecasting.backtest import generate_as_of_dates, run_rolling_origin_backtest, summarize_backtest
from demandflow.forecasting.run_statistical_backtest import build_extended_models
from demandflow.monitoring.signals import (
    anomaly_signal,
    data_quality_signal,
    forecast_accuracy_signal,
    forecast_deterioration_signal,
    overall_status,
)
from demandflow.quality.rules import findings_to_dicts, run_all_rules

logger = logging.getLogger(__name__)


def run_and_write(
    cfg: ProjectConfig | None = None,
    db_path: Path | None = None,
    out_dir: Path | None = None,
) -> dict:
    cfg = cfg or load_config()
    db_path = db_path or (cfg.paths.data_dir / "warehouse" / "demandflow.duckdb")
    if not db_path.exists():
        raise FileNotFoundError(
            f"Expected {db_path} to exist. Run demandflow.transform.build_warehouse first."
        )
    out_dir = out_dir or (cfg.paths.reports_dir / "phase10")
    out_dir.mkdir(parents=True, exist_ok=True)

    sales_path = cfg.paths.parquet_dir / "train.parquet"
    stores_path = cfg.paths.parquet_dir / "stores.parquet"
    items_path = cfg.paths.parquet_dir / "items.parquet"
    for p in (sales_path, stores_path, items_path):
        if not p.exists():
            raise FileNotFoundError(f"Expected {p} to exist. Run demandflow.ingest.convert_to_parquet first.")
    available_tables = [p.stem for p in cfg.paths.parquet_dir.glob("*.parquet")]

    # --- Data quality ---
    con = duckdb.connect()
    dq_findings = run_all_rules(con, sales_path, stores_path, items_path, available_tables)
    con.close()
    dq_sig = data_quality_signal(dq_findings)

    # --- Anomalies ---
    con = duckdb.connect(str(db_path))
    trend = trend_summary(con)
    anomalies = network_anomalies(trend["daily_totals"])
    anomaly_sig = anomaly_signal(trend["daily_totals"], anomalies)

    # --- Forecast accuracy + deterioration (fresh 5-model backtest) ---
    (min_date, max_date) = con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone()
    if min_date is None:
        con.close()
        raise ValueError("fct_sales_daily is empty -- nothing to monitor.")

    as_of_dates = generate_as_of_dates(
        min_date, max_date,
        cadence_days=cfg.forecasting.as_of_cadence_days,
        min_history_days=cfg.forecasting.min_history_days,
    )
    models = build_extended_models(cfg.forecasting.season_length_days)
    records = run_rolling_origin_backtest(con, as_of_dates, horizon=cfg.forecasting.horizon_days, models=models)
    con.close()

    backtest_summary = summarize_backtest(records)
    champion_model = backtest_summary["lower_wape_model"]
    accuracy_sig = forecast_accuracy_signal(backtest_summary["overall_by_model"], champion_model)
    deterioration_sig = forecast_deterioration_signal(records, champion_model)

    signals = [accuracy_sig, deterioration_sig, dq_sig, anomaly_sig]
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "champion_model": champion_model,
        "overall_status": overall_status([s["status"] for s in signals]),
        "signals": signals,
        "dq_findings": findings_to_dicts(dq_findings),
    }

    summary_path = out_dir / "monitoring_snapshot.json"
    summary_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s: overall_status=%s (%s)",
        summary_path, snapshot["overall_status"], ", ".join(f"{s['signal']}={s['status']}" for s in signals),
    )
    return {"summary_path": summary_path, "summary": snapshot}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Overall status: {result['summary']['overall_status']}")
    for s in result["summary"]["signals"]:
        print(f"  [{s['status']:7s}] {s['signal']}: {s['reason']}")


if __name__ == "__main__":
    _main()
