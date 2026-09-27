"""Render docs/root_cause_analysis.md from a Phase 09 RCA summary.

Same principle as every previous phase's report generator: built entirely
from reports/phase09/rca_summary.json, never hand-typed -- every "explained"
or "cause unknown" verdict below is copied from whatever the real evidence
gathering found on that run.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from demandflow.rca.data_issue_evidence import MIN_EVIDENCE_N


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f}"


def _lift(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}x"


def _data_issue_section(records: list[dict[str, Any]]) -> list[str]:
    lines = ["## Data issues investigated", ""]
    lines.append(
        "Phase 02's `rule_extreme_values` finding promised these flagged rows would be "
        "\"investigate[d] ... using business context -- promotions, holidays, known "
        "events\" here. Every statement below only ever claims a row population is "
        "*associated with* a factor, never that the factor *caused* it (CLAUDE.md Section 13)."
    )
    lines.append("")
    for r in records:
        title = r["issue"].replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"n = {r['n']}")
        if 0 < r["n"] < MIN_EVIDENCE_N:
            lines.append(
                f"_Below the n={MIN_EVIDENCE_N} screening minimum used for the conclusion "
                "below — the rates immediately below are shown for transparency, not used "
                "to draw a conclusion._"
            )
        lines.append("")
        if r["n"] > 0:
            lines.append(
                f"- Promotion-day coincidence: {_pct(r.get('promotion_rate'))} "
                f"(lift {_lift(r.get('promotion_lift'))} vs. network baseline)"
            )
            lines.append(
                f"- Holiday coincidence: {_pct(r.get('holiday_rate'))} "
                f"(lift {_lift(r.get('holiday_lift'))} vs. network baseline)"
            )
            if r.get("by_item_family"):
                top = ", ".join(f"{k}={v}" for k, v in list(r["by_item_family"].items())[:5])
                lines.append(f"- By item family: {top}")
            lines.append("")
        lines.append(r["statement"])
        lines.append("")
    return lines


def _discrepancy_section(records: list[dict[str, Any]]) -> list[str]:
    lines = ["## Forecast discrepancies investigated", ""]
    lines.append(
        "Each row below is a Phase 08 finding (CLAUDE.md Section 13: \"a forecast "
        "discrepancy ... is an investigation trigger\"). Records that share the same "
        "(dimension, segment) are grouped, since the underlying evidence is the same "
        "population of rows regardless of which Phase 08 finding flagged it."
    )
    lines.append("")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        grouped[(r["dimension"], r["segment"])].append(r)

    for (dimension, segment), group in grouped.items():
        lines.append(f"### {dimension} = {segment}")
        lines.append("")
        lines.append("**Trigger(s):**")
        for r in group:
            lines.append(f"- ({r['source_finding_category']}, model={r['model']}) {r['trigger_statement']}")
        lines.append("")

        evidence = group[0]["evidence"]
        dq, baseline = evidence["dq_flag_rates"], evidence["baseline_dq_flag_rates"]
        lines.append("**Evidence gathered:**")
        lines.append(
            f"- DQ-flag rates in this segment (n={dq['n']}): extreme value {_pct(dq.get('extreme_value_rate'))}, "
            f"return {_pct(dq.get('return_rate'))}, imputed-zero {_pct(dq.get('imputed_zero_rate'))} "
            f"— network baseline: extreme value {_pct(baseline.get('extreme_value_rate'))}, "
            f"return {_pct(baseline.get('return_rate'))}, imputed-zero {_pct(baseline.get('imputed_zero_rate'))}"
        )
        if evidence.get("segment_trend_slope") is not None:
            lines.append(
                f"- Segment demand trend: {_num(evidence['segment_trend_slope'])} units/day "
                f"vs. network trend {_num(evidence['network_trend_slope'])} units/day"
            )
        else:
            lines.append(
                "- Segment demand trend: not applicable to this dimension (not a fixed "
                "item/store population — see docs/phase_reports/phase09.md)"
            )
        lines.append("")
        lines.append(f"**Conclusion:** {group[0]['statement']}")
        lines.append("")
    return lines


def render_rca_report(summary: dict[str, Any], dataset_display_name: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []

    lines.append(f"# Root Cause Analysis — {dataset_display_name}")
    lines.append("")
    lines.append(
        "> Generated by `demandflow.reporting.generate_rca_report` from "
        f"`reports/phase09/rca_summary.json` at `{generated_at}`. Do not hand-edit — "
        "re-run the Phase 09 investigation and regenerate instead."
    )
    lines.append("")

    lines.append("## Scope")
    lines.append("")
    lines.append(
        "Two investigation triggers, per CLAUDE.md Section 3.6: **data issues** "
        "(Phase 02/03's flagged returns and extreme values) and **forecast "
        "discrepancies** (Phase 08's segment-level findings). Phase 08's "
        "`horizon_decay` and `time_trend` findings are not re-investigated here — "
        "they describe a structural pattern across the whole horizon/as-of-date axis "
        "rather than naming a specific segment, and Phase 08 already states their "
        "explanation in its own terms. This is a documented scope decision "
        "(CLAUDE.md Section 18), not an oversight."
    )
    lines.append("")
    lines.append(
        f"Champion model at investigation time: **{summary.get('champion_model', 'n/a')}**. "
        f"{summary.get('forecast_discrepancy_triggers_investigated', 0)} of "
        f"{summary.get('forecast_discrepancy_triggers_total', 0)} Phase 08 findings were "
        "segment-shaped triggers and were investigated below."
    )
    lines.append("")

    lines.extend(_data_issue_section(summary.get("data_issue_rca", [])))
    lines.extend(_discrepancy_section(summary.get("forecast_discrepancy_rca", [])))

    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Validated end-to-end only against the small committed synthetic fixture "
        "(tests/fixtures/favorita_sample/) in this sandbox, which has no Kaggle network "
        "access — not against the real Favorita dataset.\n"
        "- Evidence gathered here (promotion/holiday coincidence, DQ-flag rate, demand "
        "trend divergence) is necessarily limited to what this dataset contains — there "
        "is no stockout signal, no pricing data, and no external event calendar, so a "
        "\"cause unknown from available evidence\" verdict often reflects the dataset's "
        "own limits, not an exhaustive investigation.\n"
        "- Screening thresholds (association lift ratio, minimum evidence n, trend "
        "divergence ratio) are heuristic choices documented in "
        "`demandflow.rca.data_issue_evidence` and `demandflow.rca.discrepancy_evidence`, "
        "not JD figures.\n"
        "- Every statement here uses association language only (CLAUDE.md Section 13); "
        "none of them should be read as a confirmed cause without further investigation "
        "involving people who can inspect the operational context directly."
    )
    lines.append("")

    return "\n".join(lines)


def generate_and_write(summary_path: Path, out_path: Path, dataset_display_name: str) -> Path:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    content = render_rca_report(summary, dataset_display_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _main() -> None:
    from demandflow.config import load_config

    cfg = load_config()
    summary_path = cfg.paths.reports_dir / "phase09" / "rca_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Expected {summary_path} to exist. Run demandflow.rca.run_rca first."
        )
    out_path = Path("docs") / "root_cause_analysis.md"
    generate_and_write(summary_path, out_path, cfg.dataset.display_name)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    _main()
