"""Unit tests for Phase 11's persisted monitoring history and alerting
(demandflow.alerts.history)."""

import duckdb
import pytest

from demandflow.alerts.history import (
    compute_alerts,
    ensure_history_table,
    load_last_two_runs,
    load_recent_run_overall_statuses,
    record_snapshot,
)


def _snapshot(generated_at, signals):
    return {"generated_at": generated_at, "signals": signals}


def _signal(name, status, reason="r"):
    return {"signal": name, "status": status, "reason": reason}


@pytest.fixture
def con():
    c = duckdb.connect()
    ensure_history_table(c)
    yield c
    c.close()


# --- record_snapshot / load_last_two_runs -----------------------------------


def test_record_snapshot_assigns_increasing_run_seq(con):
    seq1 = record_snapshot(con, _snapshot("t1", [_signal("a", "OK")]))
    seq2 = record_snapshot(con, _snapshot("t2", [_signal("a", "OK")]))
    assert seq2 == seq1 + 1


def test_load_last_two_runs_empty_history_returns_none_none(con):
    previous, current = load_last_two_runs(con)
    assert previous is None
    assert current is None


def test_load_last_two_runs_single_run_returns_none_previous(con):
    record_snapshot(con, _snapshot("t1", [_signal("a", "OK")]))
    previous, current = load_last_two_runs(con)
    assert previous is None
    assert current == {"a": _signal("a", "OK")}


def test_load_last_two_runs_returns_both_after_two_runs(con):
    record_snapshot(con, _snapshot("t1", [_signal("a", "OK")]))
    record_snapshot(con, _snapshot("t2", [_signal("a", "WARN")]))
    previous, current = load_last_two_runs(con)
    assert previous["a"]["status"] == "OK"
    assert current["a"]["status"] == "WARN"


def test_load_recent_run_overall_statuses_takes_worst_per_run(con):
    record_snapshot(con, _snapshot("t1", [_signal("a", "OK"), _signal("b", "WARN")]))
    record_snapshot(con, _snapshot("t2", [_signal("a", "BREACH"), _signal("b", "OK")]))
    history = load_recent_run_overall_statuses(con)
    assert [h["overall_status"] for h in history] == ["WARN", "BREACH"]
    assert [h["run_seq"] for h in history] == [1, 2]


# --- compute_alerts (pure logic) -------------------------------------------


def test_compute_alerts_first_run_skips_ok_signals():
    current = {"a": _signal("a", "OK")}
    alerts = compute_alerts(None, current)
    assert alerts == []


def test_compute_alerts_first_run_fires_for_non_ok_signals():
    current = {"a": _signal("a", "BREACH")}
    alerts = compute_alerts(None, current)
    assert len(alerts) == 1
    assert alerts[0]["direction"] == "new"
    assert alerts[0]["previous_status"] is None
    assert alerts[0]["severity"] == "critical"


def test_compute_alerts_unchanged_status_fires_nothing():
    previous = {"a": _signal("a", "BREACH")}
    current = {"a": _signal("a", "BREACH")}
    assert compute_alerts(previous, current) == []


def test_compute_alerts_escalation_is_flagged():
    previous = {"a": _signal("a", "WARN")}
    current = {"a": _signal("a", "BREACH")}
    alerts = compute_alerts(previous, current)
    assert alerts[0]["direction"] == "escalated"
    assert alerts[0]["severity"] == "critical"


def test_compute_alerts_recovery_to_ok_is_flagged():
    previous = {"a": _signal("a", "BREACH")}
    current = {"a": _signal("a", "OK")}
    alerts = compute_alerts(previous, current)
    assert alerts[0]["direction"] == "recovered"
    assert alerts[0]["severity"] == "info"


def test_compute_alerts_de_escalation_without_full_recovery_is_flagged():
    previous = {"a": _signal("a", "BREACH")}
    current = {"a": _signal("a", "WARN")}
    alerts = compute_alerts(previous, current)
    assert alerts[0]["direction"] == "de-escalated"


def test_compute_alerts_only_fires_for_signals_that_actually_changed():
    previous = {"a": _signal("a", "OK"), "b": _signal("b", "WARN")}
    current = {"a": _signal("a", "OK"), "b": _signal("b", "BREACH")}
    alerts = compute_alerts(previous, current)
    assert len(alerts) == 1
    assert alerts[0]["signal"] == "b"
