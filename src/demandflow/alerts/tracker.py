"""Phase 11 -- discrepancy tracker.

Two upstream sources feed this tracker, both promised by earlier phases'
own text rather than invented here:

1. Phase 02's `missing_calendar_dates` finding: "Any unexplained gap is
   logged to the Phase 11 discrepancy tracker rather than silently
   zero-filled." A gap matching a documented non-trading day (per Phase
   00's public-documentation research) is resolved automatically; anything
   else stays open for a person to look at.
2. Phase 09's forecast-discrepancy RCA records that came back "cause
   unknown from available evidence" -- an investigation that ended without
   an answer is exactly the kind of item that should not just disappear
   once Phase 09's report is generated; it needs to stay visible for
   follow-up.

Idempotent by design: `upsert_tracker_items()` updates the existing row
for an already-open item (bumping `last_seen_at` / `times_seen`) instead of
inserting a duplicate every run -- the tracker's own answer to the phase
objective's "avoid unnecessary alert noise" requirement. `CREATE TABLE IF
NOT EXISTS`, never `CREATE OR REPLACE`: like monitoring_history, this
table is meant to accumulate across runs.
"""

from __future__ import annotations

import json
from typing import Any

import duckdb

# [DECISION] per Phase 00's public-documentation research on this dataset
# ([VERIFY] annotation): no sales rows are reported for December 25. Month-
# day only (not a specific year), since the pattern recurs every year this
# dataset's ~4.6-year real history spans.
KNOWN_NON_TRADING_MONTH_DAY = {"12-25"}


def calendar_gap_tracker_items(dq_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Builds one tracker item per missing-date sample from Phase 02's
    `missing_calendar_dates` rule finding (as serialized to a plain dict by
    `demandflow.quality.rules.findings_to_dicts`). Only a *sample* of up to
    20 missing dates is available (Phase 02's own `date_coverage()` check
    truncates there) -- a documented limitation, not silently pretended to
    be the complete list on a dataset with more gaps than that.
    """
    finding = next((f for f in dq_findings if f["rule_id"] == "missing_calendar_dates"), None)
    if finding is None or finding["metrics"].get("missing_dates_count", 0) == 0:
        return []

    items = []
    for date_str in finding["metrics"].get("missing_dates_sample", []):
        month_day = date_str[5:10]
        is_known = month_day in KNOWN_NON_TRADING_MONTH_DAY
        items.append({
            "natural_key": f"calendar_gap:{date_str}",
            "category": "calendar_gap",
            "severity": "info" if is_known else "warning",
            "status": "resolved_known_non_trading_day" if is_known else "open",
            "description": f"No sales rows exist for {date_str} across the entire network.",
            "evidence": {"date": date_str, "matches_known_non_trading_day": is_known},
        })
    return items


def discrepancy_rca_tracker_items(rca_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """One tracker item per (dimension, segment) forecast discrepancy whose
    Phase 09 RCA verdict was "cause unknown from available evidence" --
    deduplicated, since the same segment can be the subject of more than
    one Phase 08 finding (e.g. both a systematic_bias and a
    segment_champion_switch finding) and shares the same underlying
    evidence and verdict either way.
    """
    seen: set[str] = set()
    items = []
    for record in rca_summary.get("forecast_discrepancy_rca", []):
        if "cause unknown from available evidence" not in record["statement"]:
            continue
        key = f"forecast_discrepancy:{record['dimension']}:{record['segment']}"
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "natural_key": key,
            "category": "forecast_discrepancy",
            "severity": "warning",
            "status": "open",
            "description": record["trigger_statement"],
            "evidence": {
                "dimension": record["dimension"], "segment": record["segment"], "statement": record["statement"],
            },
        })
    return items


def ensure_tracker_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS discrepancy_tracker (
            natural_key VARCHAR, category VARCHAR, severity VARCHAR, status VARCHAR,
            description VARCHAR, evidence VARCHAR, first_seen_at VARCHAR, last_seen_at VARCHAR,
            times_seen INTEGER
        )
        """
    )


def upsert_tracker_items(
    con: duckdb.DuckDBPyConnection, items: list[dict[str, Any]], run_timestamp: str
) -> dict[str, int]:
    ensure_tracker_table(con)
    inserted, updated = 0, 0
    for item in items:
        existing = con.execute(
            "SELECT natural_key FROM discrepancy_tracker WHERE natural_key = ?", [item["natural_key"]]
        ).fetchone()
        if existing is None:
            con.execute(
                "INSERT INTO discrepancy_tracker VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    item["natural_key"], item["category"], item["severity"], item["status"],
                    item["description"], json.dumps(item["evidence"]), run_timestamp, run_timestamp, 1,
                ],
            )
            inserted += 1
        else:
            con.execute(
                """
                UPDATE discrepancy_tracker
                SET last_seen_at = ?, times_seen = times_seen + 1, status = ?, severity = ?
                WHERE natural_key = ?
                """,
                [run_timestamp, item["status"], item["severity"], item["natural_key"]],
            )
            updated += 1
    return {"inserted": inserted, "updated": updated}


def load_tracker_items(con: duckdb.DuckDBPyConnection, open_only: bool = True) -> list[dict[str, Any]]:
    ensure_tracker_table(con)
    where = "WHERE status = 'open'" if open_only else ""
    rows = con.execute(
        f"""
        SELECT natural_key, category, severity, status, description, evidence,
               first_seen_at, last_seen_at, times_seen
        FROM discrepancy_tracker
        {where}
        ORDER BY first_seen_at
        """
    ).fetchall()
    columns = [
        "natural_key", "category", "severity", "status", "description", "evidence",
        "first_seen_at", "last_seen_at", "times_seen",
    ]
    result = [dict(zip(columns, row)) for row in rows]
    for r in result:
        r["evidence"] = json.loads(r["evidence"])
    return result
