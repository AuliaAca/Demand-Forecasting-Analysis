"""Phase 04 entrypoint: runs the EDA against the already-built Phase 03
warehouse, writes reports/phase04/eda_summary.json, and renders the charts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from demandflow.analysis.charts import generate_eda_charts
from demandflow.analysis.eda import run_full_eda
from demandflow.config import ProjectConfig, load_config

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
    out_dir = out_dir or (cfg.paths.reports_dir / "phase04")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    summary = run_full_eda(con)
    con.close()

    summary_path = out_dir / "eda_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    chart_paths = generate_eda_charts(summary, out_dir / "figures")
    logger.info("Wrote %s and %d chart(s)", summary_path, len(chart_paths))
    return {"summary_path": summary_path, "chart_paths": chart_paths, "summary": summary}


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_and_write()
    print(f"Wrote {result['summary_path']}")
    for name, path in result["chart_paths"].items():
        print(f"  chart: {name} -> {path}")


if __name__ == "__main__":
    _main()
