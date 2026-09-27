"""Structural tests for Phase 12's Airflow DAG (dags/demandflow_dag.py).

These tests need `apache-airflow` importable, which this project
deliberately does NOT install into its main environment (see
docs/phase_reports/phase12.md for why) -- `pytest.importorskip` makes this
file skip cleanly under the project's normal `pytest -q` / `make test`
(the same 279 tests every other phase's `make test` run reports keep
passing), and actually run when invoked with the isolated Airflow
virtualenv's interpreter:

    .venv-airflow/bin/python -m pytest tests/unit/test_airflow_dag.py -v

Every number asserted below (24 tasks, specific dependency edges, retry
policy) was hand-verified by actually importing the DAG and inspecting it
in this session, the same "run it for real, then assert what you saw"
discipline as every previous phase's tests.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

airflow = pytest.importorskip("airflow", reason="apache-airflow is intentionally not in the main environment")

REPO_ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = REPO_ROOT / "dags"


@pytest.fixture
def dag_module(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRFLOW_HOME", str(tmp_path / "airflow_home"))
    monkeypatch.setenv("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
    monkeypatch.setenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", f"sqlite:///{tmp_path / 'airflow_home' / 'airflow.db'}")
    sys.path.insert(0, str(DAGS_DIR))
    import demandflow_dag as module

    yield module
    sys.path.remove(str(DAGS_DIR))
    sys.modules.pop("demandflow_dag", None)


EXPECTED_TASK_IDS = {
    "acquire", "convert", "profile", "select_scope", "dataset_card",
    "dq", "dq_report", "warehouse",
    "eda", "eda_report", "backtest", "backtest_report",
    "statistical_backtest", "statistical_report", "ml_backtest", "ml_report",
    "evaluate", "evaluate_report", "rca", "rca_report",
    "monitor", "monitor_report", "alerts", "alerts_report",
}

EXPECTED_EDGES = {
    "acquire": set(),
    "convert": {"acquire"},
    "profile": {"convert"},
    "select_scope": {"convert"},
    "dataset_card": {"profile", "select_scope"},
    "dq": {"convert"},
    "dq_report": {"dq"},
    "warehouse": {"select_scope"},
    "eda": {"warehouse"},
    "eda_report": {"eda"},
    "backtest": {"warehouse"},
    "backtest_report": {"backtest"},
    "statistical_backtest": {"warehouse"},
    "statistical_report": {"statistical_backtest"},
    "ml_backtest": {"warehouse"},
    "ml_report": {"ml_backtest"},
    "evaluate": {"warehouse"},
    "evaluate_report": {"evaluate"},
    "rca": {"warehouse"},
    "rca_report": {"rca"},
    "monitor": {"warehouse"},
    "monitor_report": {"monitor"},
    "alerts": {"warehouse"},
    "alerts_report": {"alerts"},
}


def test_dag_imports_without_error(dag_module):
    assert dag_module.dag.dag_id == "demandflow"


def test_dag_has_exactly_the_expected_24_tasks(dag_module):
    task_ids = {t.task_id for t in dag_module.dag.tasks}
    assert task_ids == EXPECTED_TASK_IDS
    assert len(task_ids) == 24


def test_dependency_edges_match_real_code_dependencies(dag_module):
    for task in dag_module.dag.tasks:
        upstream_ids = {u.task_id for u in task.upstream_list}
        assert upstream_ids == EXPECTED_EDGES[task.task_id], f"unexpected upstream set for {task.task_id}"


def test_warehouse_fans_out_to_eight_independent_downstream_branches(dag_module):
    # The reproducibility principle established in Phase 08 means eda,
    # backtest, statistical_backtest, ml_backtest, evaluate, rca, monitor,
    # and alerts each only need the warehouse -- not each other.
    warehouse = dag_module.operators["warehouse"]
    downstream_ids = {t.task_id for t in warehouse.downstream_list}
    assert downstream_ids == {
        "eda", "backtest", "statistical_backtest", "ml_backtest",
        "evaluate", "rca", "monitor", "alerts",
    }


def test_acquire_has_a_stronger_retry_policy_than_other_tasks(dag_module):
    acquire = dag_module.operators["acquire"]
    convert = dag_module.operators["convert"]
    assert acquire.retries == 3
    assert acquire.retry_exponential_backoff is True
    assert acquire.retry_delay == timedelta(minutes=1)
    assert convert.retries == 1
    assert convert.retry_exponential_backoff is False


def test_every_task_has_the_failure_callback_attached(dag_module):
    for task in dag_module.dag.tasks:
        assert task.on_failure_callback == dag_module._on_task_failure


def test_every_task_runs_the_correct_module_via_bash(dag_module):
    for task_id, module, _upstream in dag_module.TASKS:
        task = dag_module.operators[task_id]
        assert task.bash_command == f"{dag_module.DEMANDFLOW_PYTHON} -m {module}"


def test_dag_is_manually_triggered_and_does_not_backfill(dag_module):
    assert dag_module.dag.schedule_interval is None
    assert dag_module.dag.catchup is False


def test_on_task_failure_writes_a_structured_json_line(tmp_path, dag_module, monkeypatch):
    import json

    monkeypatch.setattr(dag_module, "FAILURE_LOG_PATH", tmp_path / "airflow_failures.jsonl")

    class _FakeTI:
        task_id = "acquire"
        try_number = 2
        max_tries = 1

    context = {
        "dag": dag_module.dag, "task_instance": _FakeTI(),
        "run_id": "manual__test", "exception": RuntimeError("boom"),
    }
    dag_module._on_task_failure(context)

    lines = (tmp_path / "airflow_failures.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["task_id"] == "acquire"
    assert record["try_number"] == 2
    assert "boom" in record["exception"]


def test_on_task_failure_never_raises_even_with_a_malformed_context(dag_module):
    dag_module._on_task_failure({})  # missing every expected key -- must not raise
