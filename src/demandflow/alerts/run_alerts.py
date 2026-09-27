"""Phase 11 entrypoint.

Runs Phase 10's monitoring check and Phase 09's root-cause analysis fresh
(same "rebuild, don't trust a stale file" principle established since
Phase 08 -- their nested output goes to private `_monitoring_rebuild/` and
`_rca_rebuild/` subfolders, never overwriting those phases' own report
directories), then:

1. Records the monitoring snapshot into the persistent `monitoring_history`
   table and computes alerts by comparing it against the previous run
   recorded there (demandflow.alerts.history).
2. Upserts open items into the persistent `discrepancy_tracker` table from
   Phase 02's missing-calendar-date gaps and Phase 09's "cause unknown"
   forecast-discrepancy findings (demandflow.alerts.tracker).

Unlike history/tracker, this module's own summary JSON is NOT meant to
accumulate -- it is Phase 11's Standard Review Package input, describing
this one run's alerts and current open-tracker state, in the same
generated-JSON-then-rendered-report pattern every previous phase uses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.alerts.history import compute_alerts, load_last_two_runs, load_recent_run_overall_statuses, record_snapshot
from demandflow.alerts.tracker import (
    calendar_gap_tracker_items,
    discrepancy_rca_tracker_items,
    load_tracker_items,
    upsert_tracker_items,
)
from demandflow.config import ProjectConfig, load_config
from demandflow.monitoring.run_monitoring import run_and_write as run_monitoring
from demandflow.rca.run_rca import run_and_write as run_rca

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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase11")
    out_dir.mkdir(parents=True, exist_ok=True)

    monitoring_result = run_monitoring(cfg, db_path=db_path, out_dir=out_dir / "_monitoring_rebuild")
    snapshot = monitoring_result["summary"]

    rca_result = run_rca(cfg, db_path=db_path, out_dir=out_dir / "_rca_rebuild")
    rca_summary = rca_result["summary"]

    with duckdb.connect(str(db_path)) as con:
        run_seq = record_snapshot(con, snapshot)
        previous_signals, current_signals = load_last_two_runs(con)
        alerts = compute_alerts(previous_signals, current_signals)
        recent_history = load_recent_run_overall_statuses(con)

        calendar_items = calendar_gap_tracker_items(snapshot["dq_findings"])
        discrepancy_items = discrepancy_rca_tracker_items(rca_summary)
        tracker_upsert_result = upsert_tracker_items(con, calendar_items + discrepancy_items, run_timestamp=snapshot["generated_at"])
        open_tracker_items = load_tracker_items(con, open_only=True)

    summary = {
        "run_seq": run_seq,
        "generated_at": snapshot["generated_at"],
        "overall_status": snapshot["overall_status"],
        "champion_model": snapshot["champion_model"],
        "alerts": alerts,
        "recent_history": recent_history,
        "tracker_upsert_result": tracker_upsert_result,
        "open_tracker_items": open_tracker_items,
    }

    summary_path = out_dir / "alerts_and_tracker_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s: run_seq=%d, %d alert(s), %d open tracker item(s)",
        summary_path, run_seq, len(alerts), len(open_tracker_items),
    )
    return {"summary_path": summary_path, "summary": summary}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    print(f"Run #{result['summary']['run_seq']}: overall status {result['summary']['overall_status']}")
    for a in result["summary"]["alerts"]:
        print(f"  ALERT [{a['severity']}] {a['message']}")
    for item in result["summary"]["open_tracker_items"]:
        print(f"  TRACKER [{item['severity']}] {item['description']} (seen {item['times_seen']}x)")


if __name__ == "__main__":
    _main()
