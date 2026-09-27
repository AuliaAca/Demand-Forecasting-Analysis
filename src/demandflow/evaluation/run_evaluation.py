"""Phase 08 entrypoint.

Rebuilds the Phase 06 rolling-origin backtest (same 5-model set -- Naive,
Seasonal Naive, SES, Croston, SBA -- same as-of-date schedule) so
fct_forecast reflects a known, deterministic model set regardless of which
backtest script last ran, rather than trusting whatever a previous phase
happened to leave in the table. It then evaluates forecast accuracy across
every JD analysis dimension Phase 04 used for demand -- SKU (via Phase 04's
intermittency classification), hub (store_type, cluster), category (item
family), campaign (promotion status), and seasonal event (holiday, payday)
-- plus horizon step and time, and turns the weak points into actionable
findings (CLAUDE.md Section 3.3).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.evaluation.segment_evaluation import (
    accuracy_trend_by_model,
    champions_by_dimension,
    evaluate_all_dimensions,
    identify_findings,
    load_scored_forecasts_with_context,
)
from demandflow.forecasting.backtest import (
    generate_as_of_dates,
    load_fct_forecast,
    run_rolling_origin_backtest,
    summarize_backtest,
    summarize_by_segment,
)
from demandflow.forecasting.run_statistical_backtest import build_extended_models, load_intermittency_classes

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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase08")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    (min_date, max_date) = con.execute("SELECT MIN(date), MAX(date) FROM fct_sales_daily").fetchone()
    if min_date is None:
        raise ValueError("fct_sales_daily is empty -- nothing to evaluate.")

    as_of_dates = generate_as_of_dates(
        min_date, max_date,
        cadence_days=cfg.forecasting.as_of_cadence_days,
        min_history_days=cfg.forecasting.min_history_days,
    )
    models = build_extended_models(cfg.forecasting.season_length_days)
    logger.info(
        "Rebuilding fct_forecast for evaluation: %d as-of date(s) x %d model(s)",
        len(as_of_dates), len(models),
    )
    records = run_rolling_origin_backtest(con, as_of_dates, horizon=cfg.forecasting.horizon_days, models=models)
    load_fct_forecast(con, records)

    intermittency_by_item = load_intermittency_classes(con)
    scored_rows = load_scored_forecasts_with_context(con)
    con.close()

    backtest_summary = summarize_backtest(records)
    overall_by_model = backtest_summary["overall_by_model"]
    champion_model = backtest_summary["lower_wape_model"]

    by_dimension = evaluate_all_dimensions(scored_rows)
    by_dimension["intermittency_class"] = summarize_by_segment(records, intermittency_by_item)

    champions_by_dim = {dim: champions_by_dimension(result) for dim, result in by_dimension.items()}
    trend_by_model = accuracy_trend_by_model(by_dimension["as_of_date"])

    evaluation = {"by_dimension": by_dimension, "accuracy_trend_by_model": trend_by_model}
    findings = identify_findings(evaluation, overall_by_model, champion_model)

    summary = {
        "as_of_dates_used": backtest_summary["as_of_dates_used"],
        "scored_as_of_dates": backtest_summary["scored_as_of_dates"],
        "total_records": backtest_summary["total_records"],
        "total_scored_records": backtest_summary["total_scored_records"],
        "overall_by_model": overall_by_model,
        "champion_model": champion_model,
        "by_dimension": by_dimension,
        "champions_by_dimension": champions_by_dim,
        "accuracy_trend_by_model": trend_by_model,
        "findings": findings,
    }

    summary_path = out_dir / "evaluation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s: champion model=%s, %d finding(s)",
        summary_path, champion_model, len(findings),
    )
    return {"summary_path": summary_path, "summary": summary}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Champion model overall: {result['summary']['champion_model']}")
    print(f"Findings: {len(result['summary']['findings'])}")
    for f in result["summary"]["findings"]:
        print(f"  [{f['category']}] {f['statement']}")


if __name__ == "__main__":
    _main()
