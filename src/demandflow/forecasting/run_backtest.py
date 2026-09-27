"""Phase 05 entrypoint: runs the rolling-origin backtest against the
already-built Phase 03 warehouse, materializes fct_forecast, and writes
reports/phase05/backtest_summary.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.forecasting.backtest import (
    generate_as_of_dates,
    load_fct_forecast,
    records_to_dicts,
    run_rolling_origin_backtest,
    summarize_backtest,
)

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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase05")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    (min_date, max_date) = con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone()
    if min_date is None:
        raise ValueError("fct_sales_daily is empty -- nothing to backtest.")

    as_of_dates = generate_as_of_dates(
        min_date, max_date,
        cadence_days=cfg.forecasting.as_of_cadence_days,
        min_history_days=cfg.forecasting.min_history_days,
    )
    logger.info("Backtesting %d as-of date(s): %s", len(as_of_dates), as_of_dates)

    records = run_rolling_origin_backtest(
        con, as_of_dates,
        horizon=cfg.forecasting.horizon_days,
        season_length=cfg.forecasting.season_length_days,
    )
    load_fct_forecast(con, records)
    con.close()

    summary = summarize_backtest(records)
    summary_path = out_dir / "backtest_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    logger.info(
        "Wrote %s: %d records, %d scored, lower-WAPE model: %s",
        summary_path, summary["total_records"], summary["total_scored_records"], summary["lower_wape_model"],
    )
    return {"summary_path": summary_path, "summary": summary, "records": records}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Lower-WAPE model: {result['summary']['lower_wape_model']}")


if __name__ == "__main__":
    _main()
