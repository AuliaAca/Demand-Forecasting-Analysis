"""Render docs/forecast_evaluation.md from a Phase 08 evaluation summary.

Same principle as every previous phase's report generator: built entirely
from reports/phase08/evaluation_summary.json, never hand-typed -- including
which segments are flagged as weak, biased, or better served by a
different model, all computed from whatever the real numbers say.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_LABELS = {
    "naive": "Naive", "seasonal_naive": "Seasonal Naive",
    "ses": "SES", "croston": "Croston", "sba": "SBA",
}
MODEL_ORDER = ["naive", "seasonal_naive", "ses", "croston", "sba"]

DIMENSION_TITLES = {
    "item_family": "Category (item family)",
    "store_type": "Hub (store type)",
    "cluster": "Hub cluster",
    "promotion": "Campaign (promotion status)",
    "holiday": "Seasonal event (holiday)",
    "payday": "Seasonal event (payday)",
    "intermittency_class": "SKU (Phase 04 intermittency classification)",
}

FINDING_CATEGORY_TITLES = {
    "weak_segment": "Segments with disproportionately high error",
    "systematic_bias": "Segments with systematic over- or under-forecasting",
    "segment_champion_switch": "Segments better served by a different model",
    "horizon_decay": "Accuracy decay with horizon",
    "time_trend": "Accuracy trend over time",
}


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


def _label(model: str | None) -> str:
    if model is None:
        return "n/a"
    return MODEL_LABELS.get(model, model)


def _metrics_row(label: str, metrics: dict[str, Any]) -> str:
    return f"| {label} | {metrics['n']} | {_num(metrics['wape'])} | {_num(metrics['mae'])} | {_pct(metrics['forecast_bias'])} |"


def _overall_table(overall_by_model: dict[str, Any]) -> list[str]:
    lines = ["| Model | n | WAPE | MAE | Bias |\n|---|---|---|---|---|"]
    for model in MODEL_ORDER:
        if model in overall_by_model:
            lines.append(_metrics_row(_label(model), overall_by_model[model]))
    return lines


def _dimension_section(dimension_key: str, dimension_result: dict[str, dict], champions: dict[str, dict]) -> list[str]:
    title = DIMENSION_TITLES.get(dimension_key, dimension_key)
    lines = [f"## By {title}", ""]
    if not dimension_result:
        lines.append("_No scored records for this dimension on this run._")
        lines.append("")
        return lines
    for segment in sorted(dimension_result, key=lambda s: (len(s), s)):
        by_model = dimension_result[segment]
        lines.append(f"### {segment}")
        lines.append("")
        lines.append("| Model | n | WAPE | MAE | Bias |\n|---|---|---|---|---|")
        for model in MODEL_ORDER:
            if model in by_model:
                lines.append(_metrics_row(_label(model), by_model[model]))
        champ = champions.get(segment, {})
        lines.append("")
        if champ.get("model"):
            lines.append(f"Lowest WAPE in this segment: **{_label(champ['model'])}** ({_num(champ['wape'])}).")
        else:
            lines.append("_Not enough scored records in this segment (fewer than the screening minimum) to name a champion._")
        lines.append("")
    return lines


def _horizon_section(by_horizon_step: dict[str, dict]) -> list[str]:
    lines = ["## Accuracy by horizon step", ""]
    lines.append(
        "How each model's error changes the further ahead it forecasts -- the "
        "JD's \"monitor forecast accuracy\" mission applied along the horizon axis, "
        "not just averaged across it."
    )
    lines.append("")
    steps = sorted((int(k) for k in by_horizon_step))
    lines.append("| Horizon step | " + " | ".join(_label(m) for m in MODEL_ORDER) + " |")
    lines.append("|---|" + "---|" * len(MODEL_ORDER))
    for step in steps:
        by_model = by_horizon_step[str(step)]
        cells = [_num(by_model.get(m, {}).get("wape")) if m in by_model else "n/a" for m in MODEL_ORDER]
        lines.append(f"| {step} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _time_trend_section(by_as_of_date: dict[str, dict], trend_by_model: dict[str, dict]) -> list[str]:
    lines = ["## Accuracy over time (as-of date trend)", ""]
    lines.append(
        "WAPE per model at each as-of date in the rolling-origin schedule, plus a "
        "simple OLS slope across them -- a positive slope means error is rising as "
        "the backtest window moves forward (accuracy deteriorating); negative means "
        "improving. With only a handful of as-of dates on this fixture, treat the "
        "direction as illustrative, not a statistically robust trend."
    )
    lines.append("")
    as_of_dates = sorted(by_as_of_date)
    lines.append("| As-of date | " + " | ".join(_label(m) for m in MODEL_ORDER) + " |")
    lines.append("|---|" + "---|" * len(MODEL_ORDER))
    for as_of in as_of_dates:
        by_model = by_as_of_date[as_of]
        cells = [_num(by_model.get(m, {}).get("wape")) if m in by_model else "n/a" for m in MODEL_ORDER]
        lines.append(f"| {as_of} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| Model | Points used | WAPE slope per as-of step | Direction |\n|---|---|---|---|")
    for model in MODEL_ORDER:
        trend = trend_by_model.get(model)
        if not trend:
            continue
        lines.append(
            f"| {_label(model)} | {trend['points_used']} | "
            f"{_num(trend['wape_ols_slope_per_as_of_step'], 4)} | {trend['direction']} |"
        )
    lines.append("")
    return lines


def _findings_section(findings: list[dict], overall_by_model: dict[str, Any], champion_model: str | None) -> list[str]:
    lines = ["## Findings and recommendations", ""]
    if not findings:
        lines.append(
            "No finding crossed this phase's screening thresholds on this run -- see "
            "docs/phase_reports/phase08.md for the thresholds and why that is a plausible "
            "outcome at this sample size, not evidence that nothing here would be worth "
            "checking on the real dataset."
        )
        lines.append("")
        return lines

    by_category: dict[str, list[dict]] = {}
    for f in findings:
        by_category.setdefault(f["category"], []).append(f)

    for category, category_findings in by_category.items():
        lines.append(f"### {FINDING_CATEGORY_TITLES.get(category, category)}")
        lines.append("")
        if category == "systematic_bias" and len(category_findings) >= 3:
            champion_overall_bias = (overall_by_model.get(champion_model) or {}).get("forecast_bias")
            if champion_overall_bias is not None and abs(champion_overall_bias) >= 0.20:
                lines.append(
                    f"_{_label(champion_model)}'s own overall bias is {_pct(champion_overall_bias)} "
                    f"(see Overall comparison above), so this bias showing up across "
                    f"{len(category_findings)} different segments below is consistent with a "
                    "network-wide pattern, not several unrelated segment-specific issues._"
                )
                lines.append("")
        for f in category_findings:
            lines.append(f"- {f['statement']} **Recommendation:** {f['recommendation']}")
        lines.append("")
    return lines


def render_evaluation_report(summary: dict[str, Any], dataset_display_name: str, horizon_days: int) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []

    lines.append(f"# Forecast Evaluation — {dataset_display_name}")
    lines.append("")
    lines.append(
        "> Generated by `demandflow.reporting.generate_evaluation_report` from "
        f"`reports/phase08/evaluation_summary.json` at `{generated_at}`. Do not hand-edit — "
        "re-run the Phase 08 evaluation and regenerate instead."
    )
    lines.append("")

    lines.append("## Scope")
    lines.append("")
    lines.append(
        "This phase evaluates the five models with a full rolling-origin backtest design "
        "(Naive, Seasonal Naive, SES, Croston, SBA — Phases 05-06), which have as-of-date x "
        "horizon-step coverage broad enough to support a segment and time breakdown. Phase 07's "
        "LightGBM model uses a deliberately different, single-final-holdout design and is not "
        "folded into this framework — a model scored at one as-of date has nothing to show on "
        "an \"accuracy over time\" axis, and mixing it in would misrepresent both results. See "
        "docs/ml_forecasting.md for its own result and docs/phase_reports/phase08.md for this "
        "scope decision."
    )
    lines.append("")
    lines.append(
        f"Grain: hub × SKU × day. Horizon: {horizon_days} days. As-of dates used: "
        f"{', '.join(summary.get('as_of_dates_used', []))} "
        f"({summary.get('total_scored_records', 0)} of {summary.get('total_records', 0)} "
        "forecast rows were scorable)."
    )
    lines.append("")

    lines.append("## Overall comparison")
    lines.append("")
    lines.extend(_overall_table(summary.get("overall_by_model", {})))
    lines.append("")
    champion = summary.get("champion_model")
    lines.append(f"**Lowest overall WAPE: {_label(champion)}.**")
    lines.append("")

    by_dimension = summary.get("by_dimension", {})
    champions_by_dim = summary.get("champions_by_dimension", {})
    for dim in ["item_family", "store_type", "cluster", "promotion", "holiday", "payday", "intermittency_class"]:
        if dim in by_dimension:
            lines.extend(_dimension_section(dim, by_dimension[dim], champions_by_dim.get(dim, {})))

    if "horizon_step" in by_dimension:
        lines.extend(_horizon_section(by_dimension["horizon_step"]))

    if "as_of_date" in by_dimension:
        lines.extend(_time_trend_section(by_dimension["as_of_date"], summary.get("accuracy_trend_by_model", {})))

    lines.extend(_findings_section(summary.get("findings", []), summary.get("overall_by_model", {}), champion))

    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Validated end-to-end only against the small committed synthetic fixture "
        "(tests/fixtures/favorita_sample/) in this sandbox, which has no Kaggle network "
        "access — not against the real Favorita dataset. All numbers above are fixture "
        "numbers, not real-data results.\n"
        "- Screening thresholds (weak-segment WAPE ratio, systematic-bias cutoff, minimum "
        "scored rows per segment) are heuristic choices documented in "
        "`demandflow.evaluation.segment_evaluation`, not JD figures.\n"
        "- Pricing is not evaluated as a dimension — no item-level pricing exists in this "
        "dataset (same limitation Phase 04 documented for demand analysis).\n"
        "- The promotion breakdown excludes forecast rows whose target-date promotion status "
        "is unknown in the raw source data, rather than defaulting them to \"not promoted\".\n"
        "- The as-of-date accuracy trend is illustrative only, given how few as-of dates this "
        "project's development scope produces; it is not a statistically robust drift estimate."
    )
    lines.append("")

    return "\n".join(lines)


def generate_and_write(summary_path: Path, out_path: Path, dataset_display_name: str, horizon_days: int) -> Path:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    content = render_evaluation_report(summary, dataset_display_name, horizon_days)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _main() -> None:
    from demandflow.config import load_config

    cfg = load_config()
    summary_path = cfg.paths.reports_dir / "phase08" / "evaluation_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Expected {summary_path} to exist. Run demandflow.evaluation.run_evaluation first."
        )
    out_path = Path("docs") / "forecast_evaluation.md"
    generate_and_write(summary_path, out_path, cfg.dataset.display_name, cfg.forecasting.horizon_days)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    _main()
