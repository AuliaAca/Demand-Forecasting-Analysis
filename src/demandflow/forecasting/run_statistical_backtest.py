"""Phase 06 entrypoint: extends Phase 05's rolling-origin backtest with the
statistical models (SES, Croston, SBA), and evaluates them broken out by
Phase 04's intermittency classification -- the empirical test of this
phase's own justification (see demandflow.forecasting.statistical's module
docstring): do Croston-family methods actually help more on the
intermittent/lumpy items they were built for?

Reuses the exact same run_rolling_origin_backtest as Phase 05 (same
leakage-safe loop, same as-of-date schedule) with an extended `models`
dict, and reloads fct_forecast with the full 5-model result -- a superset
of Phase 05's, in the same table.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.forecasting.backtest import (
    default_models,
    generate_as_of_dates,
    load_fct_forecast,
    run_rolling_origin_backtest,
    summarize_backtest,
    summarize_by_segment,
)
from demandflow.forecasting.statistical import croston_forecast, ses_forecast

logger = logging.getLogger(__name__)

MODEL_SES = "ses"
MODEL_CROSTON = "croston"
MODEL_SBA = "sba"


def build_extended_models(season_length: int) -> dict:
    """Phase 05's Naive + Seasonal Naive, plus SES, Croston, and SBA -- one
    models dict for run_rolling_origin_backtest."""
    models = dict(default_models(season_length))

    def _ses(history, horizon):
        return ses_forecast(history, horizon) if history else None

    def _croston(history, horizon):
        return croston_forecast(history, horizon, variant="croston") if history else None

    def _sba(history, horizon):
        return croston_forecast(history, horizon, variant="sba") if history else None

    models[MODEL_SES] = _ses
    models[MODEL_CROSTON] = _croston
    models[MODEL_SBA] = _sba
    return models


def load_intermittency_classes(con: duckdb.DuckDBPyConnection) -> dict[int, str]:
    """item_nbr -> Phase 04 intermittency class, reusing that phase's own
    classification rather than recomputing a different one here."""
    from demandflow.analysis.eda import sku_velocity_and_intermittency

    rows = sku_velocity_and_intermittency(con)
    return {r["item_nbr"]: r["intermittency_class"] for r in rows}


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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase06")
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
    models = build_extended_models(cfg.forecasting.season_length_days)
    logger.info("Backtesting %d as-of date(s) x %d model(s): %s", len(as_of_dates), len(models), sorted(models))

    records = run_rolling_origin_backtest(con, as_of_dates, horizon=cfg.forecasting.horizon_days, models=models)
    load_fct_forecast(con, records)  # supersedes Phase 05's 2-model fct_forecast with the full 5-model set

    intermittency_by_item = load_intermittency_classes(con)
    con.close()

    summary = summarize_backtest(records)
    summary["by_intermittency_class"] = summarize_by_segment(records, intermittency_by_item)

    summary_path = out_dir / "statistical_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    logger.info(
        "Wrote %s: %d records, %d scored, lower-WAPE model overall: %s",
        summary_path, summary["total_records"], summary["total_scored_records"], summary["lower_wape_model"],
    )
    return {"summary_path": summary_path, "summary": summary, "records": records}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Lower-WAPE model overall: {result['summary']['lower_wape_model']}")
    for segment, by_model in result["summary"]["by_intermittency_class"].items():
        wapes = {m: v["wape"] for m, v in by_model.items() if v["wape"] is not None}
        best = min(wapes, key=wapes.get) if wapes else "n/a"
        print(f"  {segment}: lower-WAPE model = {best}  ({wapes})")


if __name__ == "__main__":
    _main()
