"""Phase 10 -- Monitoring: automated health signals.

The JD mission this phase exists for is "Monitor forecast accuracy" (and,
more broadly, CLAUDE.md's position-purpose summary: "monitoring" as one of
the things the automated tools this role builds are for). Everything
built in Phases 02-09 already *computes* the relevant numbers -- DQ
severities, network anomalies, backtest WAPE, per-as-of-date accuracy.
What none of it does yet is turn a number into an automated PASS/WARN/
BREACH verdict against an explicit, justified threshold. That is this
module's entire job: four signal functions, each taking numbers already
computed elsewhere and returning one status plus the reason for it.

Scope boundary (CLAUDE.md Section 18, and the project's own phase list --
"10 Monitoring" is a separate phase from "11 Alerts / Trackers"): this
module answers "what is the status right now, and why" for one point-in-
time run. It does not persist a history of runs, does not decide who gets
notified, and does not write to any external channel -- logging a
snapshot over time and turning a BREACH into an actual alert is Phase 11's
job. Every threshold below is a `[DECISION]`, not a JD figure, in the same
spirit as Phase 04's ABC cutoffs and anomaly z-threshold, or Phase 08's
weak-segment ratio.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from demandflow.forecasting.backtest import ForecastRecord
from demandflow.forecasting.metrics import wape
from demandflow.quality.rules import DQFinding

OK = "OK"
WARN = "WARN"
BREACH = "BREACH"
UNKNOWN = "UNKNOWN"

# Ranked worst-to-best is BREACH > WARN > UNKNOWN > OK: "we don't know" is
# deliberately ranked above "everything is fine" in overall_status(), so a
# signal that couldn't be computed never gets silently absorbed into a
# clean bill of health.
_SEVERITY_RANK = {OK: 0, UNKNOWN: 1, WARN: 2, BREACH: 3}


def overall_status(statuses: list[str]) -> str:
    if not statuses:
        return UNKNOWN
    return max(statuses, key=lambda s: _SEVERITY_RANK[s])


# --- Forecast accuracy ------------------------------------------------------

# [DECISION] WAPE >= 1.0 means total absolute error is at least as large as
# total actual volume -- a conventional, scale-free "this forecast is no
# better than predicting a constant near zero" sanity line, not a JD figure.
FORECAST_ACCURACY_WAPE_WARN = 1.0
# [DECISION] WAPE >= 1.5: error exceeds volume by half again -- a forecast
# this far off is actively misleading for inventory decisions, not merely
# imprecise.
FORECAST_ACCURACY_WAPE_BREACH = 1.5


def forecast_accuracy_signal(overall_by_model: dict[str, Any], champion_model: str | None) -> dict[str, Any]:
    """Is the current best (lowest-WAPE) model's overall accuracy within an
    acceptable range at all -- independent of any other model, any trend,
    any segment. The most basic "is this usable" check."""
    wape_value = (overall_by_model.get(champion_model) or {}).get("wape") if champion_model else None
    if champion_model is None or wape_value is None:
        return {
            "signal": "forecast_accuracy", "status": UNKNOWN, "champion_model": champion_model, "wape": None,
            "reason": "No champion model with a computable overall WAPE was available.",
        }
    if wape_value >= FORECAST_ACCURACY_WAPE_BREACH:
        status = BREACH
    elif wape_value >= FORECAST_ACCURACY_WAPE_WARN:
        status = WARN
    else:
        status = OK
    return {
        "signal": "forecast_accuracy", "status": status, "champion_model": champion_model, "wape": wape_value,
        "warn_threshold": FORECAST_ACCURACY_WAPE_WARN, "breach_threshold": FORECAST_ACCURACY_WAPE_BREACH,
        "reason": f"{champion_model}'s overall WAPE is {wape_value:.3f} "
        f"(WARN >= {FORECAST_ACCURACY_WAPE_WARN}, BREACH >= {FORECAST_ACCURACY_WAPE_BREACH}).",
    }


# --- Forecast deterioration --------------------------------------------------

# [DECISION] the most recent as-of date's WAPE being >=20% worse than the
# pooled WAPE across every earlier as-of date is treated as a warning sign;
# >=50% worse as a breach -- the same relative-lift-threshold pattern used
# throughout this project (Phase 08's WEAK_SEGMENT_WAPE_RATIO, Phase 09's
# ASSOCIATION_LIFT_THRESHOLD), applied here to accuracy over time instead
# of accuracy across a segment.
DETERIORATION_WARN_RATIO = 1.2
DETERIORATION_BREACH_RATIO = 1.5


def forecast_deterioration_signal(records: list[ForecastRecord], champion_model: str | None) -> dict[str, Any]:
    """Compares the champion model's WAPE at the most recent as-of date
    (the "final holdout") against its own WAPE pooled across every earlier
    as-of date -- directly the JD's "Where is forecast accuracy
    deteriorating?" question, answered for the model actually in use
    rather than in the abstract.
    """
    if champion_model is None:
        return {"signal": "forecast_deterioration", "status": UNKNOWN, "champion_model": None,
                "reason": "No champion model identified."}

    scored = [r for r in records if r.is_scored and r.model == champion_model]
    as_of_dates = sorted({r.as_of_date for r in scored})
    if len(as_of_dates) < 2:
        return {
            "signal": "forecast_deterioration", "status": UNKNOWN, "champion_model": champion_model,
            "as_of_dates_with_scored_forecasts": len(as_of_dates),
            "reason": f"Only {len(as_of_dates)} as-of date(s) have scored {champion_model} forecasts -- "
            "not enough history yet to compare recent vs. prior performance.",
        }

    final_as_of = as_of_dates[-1]
    final_pairs = [(r.actual, r.forecast) for r in scored if r.as_of_date == final_as_of]
    prior_pairs = [(r.actual, r.forecast) for r in scored if r.as_of_date != final_as_of]
    final_wape = wape(final_pairs)
    prior_wape = wape(prior_pairs)

    if final_wape is None or prior_wape is None:
        return {
            "signal": "forecast_deterioration", "status": UNKNOWN, "champion_model": champion_model,
            "final_holdout_as_of_date": final_as_of,
            "reason": "Insufficient scored volume in one of the two periods to compute a comparable WAPE.",
        }

    ratio = final_wape / prior_wape if prior_wape else None
    if ratio is None:
        status = UNKNOWN
        reason = "Prior-period WAPE is zero (no error at all across every earlier as-of date) -- ratio is undefined."
    elif ratio >= DETERIORATION_BREACH_RATIO:
        status = BREACH
        reason = None
    elif ratio >= DETERIORATION_WARN_RATIO:
        status = WARN
        reason = None
    else:
        status = OK
        reason = None
    if reason is None:
        reason = (
            f"Most recent as-of date's ({final_as_of}) WAPE ({final_wape:.3f}) is {ratio:.2f}x the pooled "
            f"WAPE across the {len(as_of_dates) - 1} earlier as-of date(s) ({prior_wape:.3f}) "
            f"(WARN >= {DETERIORATION_WARN_RATIO}x, BREACH >= {DETERIORATION_BREACH_RATIO}x)."
        )

    return {
        "signal": "forecast_deterioration", "status": status, "champion_model": champion_model,
        "final_holdout_as_of_date": final_as_of, "final_holdout_wape": final_wape, "prior_periods_wape": prior_wape,
        "ratio": ratio, "warn_ratio": DETERIORATION_WARN_RATIO, "breach_ratio": DETERIORATION_BREACH_RATIO,
        "reason": reason,
    }


# --- Data quality -------------------------------------------------------------

# [DECISION] rolls Phase 02's existing 6-level DQ severity scale down to
# this module's 4-level monitoring vocabulary -- PASS/INFO/LOW are all
# "nothing actionable right now", MEDIUM warrants attention, HIGH/CRITICAL
# are a breach. Phase 02 already justifies each rule's own severity; this
# mapping is only about which of those severities should stop a pipeline
# run vs. merely be visible.
_DQ_SEVERITY_TO_STATUS = {
    "PASS": OK, "INFO": OK, "LOW": OK, "MEDIUM": WARN, "HIGH": BREACH, "CRITICAL": BREACH,
}


def data_quality_signal(dq_findings: list[DQFinding]) -> dict[str, Any]:
    """Rolls up Phase 02's rule-level findings (already computed, already
    justified per-rule) into one overall DQ status for this run."""
    if not dq_findings:
        return {"signal": "data_quality", "status": UNKNOWN, "reason": "No DQ findings were available to roll up."}

    mapped = [(f.rule_id, f.severity, _DQ_SEVERITY_TO_STATUS.get(f.severity, UNKNOWN)) for f in dq_findings]
    status = overall_status([m[2] for m in mapped])
    driving_rules = [rule_id for rule_id, _sev, st in mapped if st == status]
    severity_counts: dict[str, int] = {}
    for _rule_id, sev, _st in mapped:
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "signal": "data_quality", "status": status,
        "rule_count": len(dq_findings),
        "severity_counts": severity_counts,
        "driving_rules": driving_rules if status != OK else [],
        "reason": (
            f"Worst DQ rule severity observed maps to {status}: {', '.join(driving_rules)}."
            if status != OK
            else "Every DQ rule is PASS, INFO, or LOW severity."
        ),
    }


# --- Anomalies ------------------------------------------------------------

# [DECISION] a one-week look-back window -- the same season_length_days
# convention already used for the rolling-origin backtest (configs/
# project.yaml), reused here as "how far back counts as 'recent'" rather
# than introducing an unrelated number.
ANOMALY_MONITORING_RECENT_DAYS = 7


def anomaly_signal(
    daily_totals: list[dict[str, Any]],
    all_anomalies: list[dict[str, Any]],
    recent_days: int = ANOMALY_MONITORING_RECENT_DAYS,
) -> dict[str, Any]:
    """Restricts Phase 04's network_anomalies() (already computed, a
    z-score screen over the whole observed history) to the most recent
    window -- a "did anything already-defined-as-anomalous happen lately"
    check, not a re-detection of anomalies with a different method.
    """
    if not daily_totals:
        return {"signal": "anomalies", "status": UNKNOWN, "reason": "No daily totals were available."}

    max_date = max(row["date"] for row in daily_totals)
    max_d = _dt.date.fromisoformat(max_date)
    cutoff = (max_d - _dt.timedelta(days=recent_days - 1)).isoformat()
    recent = [a for a in all_anomalies if a["date"] >= cutoff]

    if len(recent) >= 2:
        status = BREACH
    elif len(recent) == 1:
        status = WARN
    else:
        status = OK

    return {
        "signal": "anomalies", "status": status,
        "recent_window_start": cutoff, "recent_window_end": max_date, "recent_days": recent_days,
        "recent_anomaly_count": len(recent), "recent_anomalies": recent,
        "total_anomalies_all_history": len(all_anomalies),
        "reason": f"{len(recent)} network-wide anomaly day(s) (|z| > threshold) in the most recent "
        f"{recent_days} day(s) of observed data (out of {len(all_anomalies)} across the full history).",
    }
