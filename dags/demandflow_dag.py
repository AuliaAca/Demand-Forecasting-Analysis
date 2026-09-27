"""DemandFlow's Airflow DAG -- Phase 12.

CLAUDE.md Section 5 lists Airflow as a JD *bonus* exposure signal, not a
requirement, and Phase 12's own objective is conditional: implement it
"only if it provides meaningful evidence." The evidence this DAG provides
is orchestration itself -- dependencies, retries, and failure handling
across the 24 tasks Phases 01-11 already built and validated individually
(every `make <target>` in the repo's Makefile, run 279 times over via this
project's unit tests and 25-step fixture smoke test). Phase 12 does not
re-implement or duplicate that logic; it wires it into a real, importable,
executable Airflow DAG.

Design decisions (all documented further in docs/phase_reports/phase12.md):

- **No `demandflow` import here, ever.** Every task is a BashOperator
  running `python -m demandflow.<module>` -- the exact command its
  Makefile target already runs. This keeps DAG *parsing* independent of
  whether duckdb/pandas/lightgbm/demandflow are importable in whatever
  Python environment is running the Airflow scheduler itself (this
  project deliberately installs Airflow into its own isolated virtualenv,
  `.venv-airflow/`, never into the project's main environment -- see
  Phase 12's review package for why). `DEMANDFLOW_PYTHON` (default
  `python3`) controls which interpreter actually executes each task.

- **The dependency graph reflects real code dependencies, not the phase
  numbering.** Phases 08-11 each independently rebuild whatever backtest
  or evaluation state they need directly from the warehouse (a
  reproducibility principle established in Phase 08's own review
  package) rather than reading another phase's output file. The result:
  eda, backtest, statistical_backtest, ml_backtest, evaluate, rca,
  monitor, and alerts are all *siblings* that only depend on `warehouse`,
  not a strict 04-05-06-07-08-09-10-11 chain. This DAG represents that
  honestly (a wide fan-out under `warehouse`) rather than adding artificial
  edges to look more sequential than the code actually is.

- **Retries + failure handling.** Every task gets a baseline retry policy;
  `acquire` (the one task that makes a real network call, to the Kaggle
  API) gets more retries with exponential backoff, since a network hiccup
  is exactly the failure mode retrying can fix. `_on_task_failure` writes
  one structured JSON line per failed task try to
  reports/airflow_failures.jsonl -- real, inspectable evidence of the
  failure path, on top of Airflow's own task logs.

- **Reproducibility.** `schedule=None`, `catchup=False`, a fixed
  `start_date` -- this sandbox has no live daily data feed and no real
  Kaggle credentials, so implying a working production cron schedule would
  misrepresent what has actually been run. See the review package for what
  a real production schedule would look like.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

REPO_ROOT = Path(__file__).resolve().parents[1]
FAILURE_LOG_PATH = REPO_ROOT / "reports" / "airflow_failures.jsonl"

# [DECISION] the interpreter that actually runs `python -m demandflow...`.
# Defaults to whatever `python3` resolves to on the Airflow worker's PATH;
# override via the DEMANDFLOW_PYTHON environment variable (or an Airflow
# Variable of the same name) to point at the project's own interpreter when
# Airflow itself runs from a separate virtualenv, as it does in this
# project (see module docstring).
DEMANDFLOW_PYTHON = os.environ.get("DEMANDFLOW_PYTHON", "python3")

# (task_id, demandflow module, upstream task_ids). One row per Makefile
# target from `acquire` through `alerts-report` -- see the Makefile itself
# for the one-to-one mapping.
TASKS: list[tuple[str, str, list[str]]] = [
    ("acquire", "demandflow.ingest.acquire_favorita", []),
    ("convert", "demandflow.ingest.convert_to_parquet", ["acquire"]),
    ("profile", "demandflow.profiling.profile_favorita", ["convert"]),
    ("select_scope", "demandflow.scope.select_dev_scope", ["convert"]),
    ("dataset_card", "demandflow.reporting.generate_dataset_card", ["profile", "select_scope"]),
    ("dq", "demandflow.quality.rules", ["convert"]),
    ("dq_report", "demandflow.reporting.generate_dq_report", ["dq"]),
    ("warehouse", "demandflow.transform.build_warehouse", ["select_scope"]),
    ("eda", "demandflow.analysis.run_eda", ["warehouse"]),
    ("eda_report", "demandflow.reporting.generate_eda_report", ["eda"]),
    ("backtest", "demandflow.forecasting.run_backtest", ["warehouse"]),
    ("backtest_report", "demandflow.reporting.generate_forecast_baselines_report", ["backtest"]),
    ("statistical_backtest", "demandflow.forecasting.run_statistical_backtest", ["warehouse"]),
    ("statistical_report", "demandflow.reporting.generate_statistical_models_report", ["statistical_backtest"]),
    ("ml_backtest", "demandflow.forecasting.run_ml_backtest", ["warehouse"]),
    ("ml_report", "demandflow.reporting.generate_ml_report", ["ml_backtest"]),
    ("evaluate", "demandflow.evaluation.run_evaluation", ["warehouse"]),
    ("evaluate_report", "demandflow.reporting.generate_evaluation_report", ["evaluate"]),
    ("rca", "demandflow.rca.run_rca", ["warehouse"]),
    ("rca_report", "demandflow.reporting.generate_rca_report", ["rca"]),
    ("monitor", "demandflow.monitoring.run_monitoring", ["warehouse"]),
    ("monitor_report", "demandflow.reporting.generate_monitoring_report", ["monitor"]),
    ("alerts", "demandflow.alerts.run_alerts", ["warehouse"]),
    ("alerts_report", "demandflow.reporting.generate_alerts_report", ["alerts"]),
]


def _on_task_failure(context: dict) -> None:
    """Appends one JSON line per failed task attempt -- concrete, inspectable
    evidence that failure handling actually engages, beyond Airflow's own
    task-instance logs. Never raises: a broken failure handler must not
    mask the original failure or crash the scheduler.
    """
    try:
        ti = context["task_instance"]
        record = {
            "dag_id": context["dag"].dag_id,
            "task_id": ti.task_id,
            "run_id": context.get("run_id"),
            "try_number": ti.try_number,
            "max_tries": ti.max_tries,
            "exception": str(context.get("exception")),
        }
        FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FAILURE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001 -- a failing failure-handler must never mask the real failure
        pass


default_args = {
    "owner": "demandflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "on_failure_callback": _on_task_failure,
}

with DAG(
    dag_id="demandflow",
    description="DemandFlow: acquire -> warehouse -> forecasting/evaluation/RCA/monitoring/alerts",
    default_args=default_args,
    schedule=None,  # [DECISION] manual trigger only -- see module docstring
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["demandflow", "portfolio"],
    doc_md=__doc__,
) as dag:
    operators: dict[str, BashOperator] = {}
    for task_id, module, _upstream in TASKS:
        task_kwargs: dict = {}
        if task_id == "acquire":
            # The one task making a real network call (the Kaggle API) --
            # a transient failure there is exactly what a retry can fix,
            # so it gets more attempts and exponential backoff rather than
            # the flat default every other (purely local, deterministic)
            # task uses.
            task_kwargs = {
                "retries": 3,
                "retry_delay": timedelta(minutes=1),
                "retry_exponential_backoff": True,
                "max_retry_delay": timedelta(minutes=10),
            }
        operators[task_id] = BashOperator(
            task_id=task_id,
            bash_command=f"{DEMANDFLOW_PYTHON} -m {module}",
            **task_kwargs,
        )

    for task_id, _module, upstream in TASKS:
        for up in upstream:
            operators[up] >> operators[task_id]
