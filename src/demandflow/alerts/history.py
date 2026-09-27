"""Phase 11 -- persisted monitoring history and alerts computed from it.

Phase 10 explicitly deferred two things: persisting a snapshot history
across runs, and turning a status into an actual alert someone would act
on ("logging results over time and raising an actual alert is Phase 11's
job" -- docs/phase_reports/phase10.md). This module is that follow-through.

`record_snapshot()` appends the current run's four signals to a
`monitoring_history` table in the warehouse -- a genuine, append-only time
series (`CREATE TABLE IF NOT EXISTS`, never `CREATE OR REPLACE`: this is
the first table in the project meant to accumulate across runs rather than
be rebuilt fresh each time). `compute_alerts()` then compares the newest
run against the one immediately before it and fires an alert only on a
STATUS TRANSITION for a signal -- the phase objective's "avoid unnecessary
alert noise" requirement, satisfied by construction: an unchanged status
between two consecutive runs never produces an alert, no matter how many
times the pipeline re-runs while the same issue persists.
"""

from __future__ import annotations

import json
from typing import Any

import duckdb

from demandflow.monitoring.signals import SEVERITY_RANK

# [DECISION] maps a signal's status to an alert's severity label -- a
# recovery to OK is still worth surfacing (it's news), just at low
# severity, rather than being silently dropped like an unchanged OK would be.
ALERT_SEVERITY = {"BREACH": "critical", "WARN": "warning", "UNKNOWN": "warning", "OK": "info"}


def ensure_history_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring_history (
            run_seq INTEGER, generated_at VARCHAR, signal VARCHAR, status VARCHAR,
            reason VARCHAR, details VARCHAR
        )
        """
    )


def record_snapshot(con: duckdb.DuckDBPyConnection, snapshot: dict[str, Any]) -> int:
    """Appends one row per signal for this run, tagged with a monotonic
    run_seq -- DuckDB tables carry no implicit row order, so an explicit
    sequence column is what lets `load_last_two_runs` reliably identify
    "the previous run" later."""
    ensure_history_table(con)
    (next_seq,) = con.execute("SELECT COALESCE(MAX(run_seq), 0) + 1 FROM monitoring_history").fetchone()
    for s in snapshot["signals"]:
        con.execute(
            "INSERT INTO monitoring_history VALUES (?, ?, ?, ?, ?, ?)",
            [next_seq, snapshot["generated_at"], s["signal"], s["status"], s["reason"], json.dumps(s)],
        )
    return int(next_seq)


def load_last_two_runs(
    con: duckdb.DuckDBPyConnection,
) -> tuple[dict[str, dict] | None, dict[str, dict] | None]:
    """Returns (previous_run_signals, current_run_signals), each a
    {signal_name: signal_dict} mapping, or (None, None) if the history
    table is empty, or (None, current) if only one run has ever been
    recorded."""
    ensure_history_table(con)
    seqs = [r[0] for r in con.execute(
        "SELECT DISTINCT run_seq FROM monitoring_history ORDER BY run_seq DESC LIMIT 2"
    ).fetchall()]
    if not seqs:
        return None, None

    def _load(seq: int) -> dict[str, dict]:
        rows = con.execute(
            "SELECT signal, details FROM monitoring_history WHERE run_seq = ?", [seq]
        ).fetchall()
        return {signal: json.loads(details) for signal, details in rows}

    current = _load(seqs[0])
    previous = _load(seqs[1]) if len(seqs) > 1 else None
    return previous, current


def load_recent_run_overall_statuses(con: duckdb.DuckDBPyConnection, limit: int = 10) -> list[dict[str, Any]]:
    """One row per recent run: run_seq, generated_at, and the worst status
    across that run's signals -- reuses the same worst-of rule Phase 10's
    overall_status() applies within a single run, applied here across the
    signals recorded for each historical run."""
    from demandflow.monitoring.signals import overall_status

    ensure_history_table(con)
    run_seqs = [r[0] for r in con.execute(
        "SELECT DISTINCT run_seq FROM monitoring_history ORDER BY run_seq DESC LIMIT ?", [limit]
    ).fetchall()]
    result = []
    for seq in run_seqs:
        rows = con.execute(
            "SELECT generated_at, status FROM monitoring_history WHERE run_seq = ?", [seq]
        ).fetchall()
        generated_at = rows[0][0] if rows else None
        result.append({
            "run_seq": seq, "generated_at": generated_at,
            "overall_status": overall_status([r[1] for r in rows]),
        })
    return sorted(result, key=lambda r: r["run_seq"])


def _direction(previous_status: str | None, current_status: str) -> str:
    if previous_status is None:
        return "new"
    if current_status == "OK" and previous_status != "OK":
        return "recovered"
    if SEVERITY_RANK[current_status] > SEVERITY_RANK[previous_status]:
        return "escalated"
    if SEVERITY_RANK[current_status] < SEVERITY_RANK[previous_status]:
        return "de-escalated"
    return "unchanged"  # unreachable in compute_alerts (filtered out before this point), kept for completeness


def compute_alerts(previous_signals: dict[str, dict] | None, current_signals: dict[str, dict]) -> list[dict[str, Any]]:
    """One alert per signal whose status differs from the previous
    recorded run. On the very first run ever (previous_signals is None), a
    signal that starts OK is not alerted on -- there is nothing new to
    report about a clean bill of health -- but a signal that starts WARN/
    BREACH/UNKNOWN is, since that is real, actionable information the
    first time it is seen.
    """
    alerts = []
    for name, current in current_signals.items():
        previous = (previous_signals or {}).get(name)
        previous_status = previous["status"] if previous else None
        current_status = current["status"]

        if previous is None and current_status == "OK":
            continue
        if previous is not None and current_status == previous_status:
            continue

        direction = _direction(previous_status, current_status)
        alerts.append({
            "signal": name,
            "previous_status": previous_status,
            "status": current_status,
            "direction": direction,
            "severity": ALERT_SEVERITY.get(current_status, "warning"),
            "message": f"{name}: {previous_status or '(no prior run)'} -> {current_status} ({direction}). {current['reason']}",
            "evidence": current,
        })
    return alerts
