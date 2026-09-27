"""Phase 09 entrypoint.

Runs both RCA investigations against the already-built Phase 03 warehouse.
Part A (data issues -- returns and extreme values, with business context)
needs only the warehouse itself: Phase 03's staging layer already carries
the is_return/is_extreme_value flags Phase 02 defined. Part B (forecast
discrepancies) needs Phase 08's evaluation findings and scored-forecast
rows; rather than trusting a stale reports/phase08/evaluation_summary.json
left by a previous run, this phase regenerates that evaluation itself (the
same "rebuild, don't trust the file" principle Phase 08 established for
fct_forecast), writing its own private copy under
reports/phase09/_evaluation_rebuild/ rather than overwriting Phase 08's own
report directory.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.config import ProjectConfig, load_config
from demandflow.evaluation.run_evaluation import run_and_write as run_evaluation
from demandflow.evaluation.segment_evaluation import load_scored_forecasts_with_context
from demandflow.forecasting.run_statistical_backtest import load_intermittency_classes
from demandflow.rca.data_issue_evidence import (
    build_data_issue_rca,
    gather_data_issue_evidence,
    load_baseline_rates,
    load_flagged_rows_with_context,
)
from demandflow.rca.discrepancy_evidence import (
    build_discrepancy_rca,
    dq_flag_rates,
    gather_discrepancy_evidence,
    network_trend_slope,
)

logger = logging.getLogger(__name__)

# Only these three finding categories name a specific (dimension, segment)
# pair to investigate. horizon_decay and time_trend describe a structural
# pattern across the whole horizon/as-of-date axis, not a segment, and
# Phase 08 already gives their explanation in its own terms (a lag-based
# model's error grows with horizon; too few as-of dates for a robust
# trend estimate) -- they are not re-investigated here as a documented
# scope choice (CLAUDE.md Section 18), not an oversight.
DISCREPANCY_FINDING_CATEGORIES = {"weak_segment", "systematic_bias", "segment_champion_switch"}


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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase09")
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Part A: data issues (returns, extreme values) ---
    con = duckdb.connect(str(db_path))
    flagged_rows = load_flagged_rows_with_context(con)
    baseline_business_context = load_baseline_rates(con)
    con.close()

    data_issue_evidence = gather_data_issue_evidence(flagged_rows, baseline_business_context)
    data_issue_records = build_data_issue_rca(data_issue_evidence)

    # --- Part B: forecast discrepancies (Phase 08's findings) ---
    eval_result = run_evaluation(cfg, db_path=db_path, out_dir=out_dir / "_evaluation_rebuild")
    eval_summary = eval_result["summary"]
    all_findings = eval_summary.get("findings", [])
    triggers = [f for f in all_findings if f["category"] in DISCREPANCY_FINDING_CATEGORIES]

    con = duckdb.connect(str(db_path))
    scored_rows = load_scored_forecasts_with_context(con)
    item_to_class = load_intermittency_classes(con)
    trend = network_trend_slope(con)
    baseline_dq_rates = dq_flag_rates(scored_rows)

    discrepancy_records = []
    for finding in triggers:
        evidence = gather_discrepancy_evidence(con, finding, scored_rows, baseline_dq_rates, trend, item_to_class)
        discrepancy_records.append(build_discrepancy_rca(finding, evidence))
    con.close()

    summary = {
        "data_issue_rca": data_issue_records,
        "forecast_discrepancy_rca": discrepancy_records,
        "forecast_discrepancy_triggers_total": len(all_findings),
        "forecast_discrepancy_triggers_investigated": len(triggers),
        "champion_model": eval_summary.get("champion_model"),
    }

    summary_path = out_dir / "rca_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s: %d data-issue record(s), %d forecast-discrepancy record(s)",
        summary_path, len(data_issue_records), len(discrepancy_records),
    )
    return {"summary_path": summary_path, "summary": summary}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    for record in result["summary"]["data_issue_rca"]:
        print(f"  [data_issue:{record['issue']}] {record['statement']}")
    for record in result["summary"]["forecast_discrepancy_rca"]:
        print(f"  [discrepancy:{record['dimension']}={record['segment']}] {record['statement']}")


if __name__ == "__main__":
    _main()
