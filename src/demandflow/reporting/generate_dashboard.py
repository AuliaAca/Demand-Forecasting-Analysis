"""Phase 14 -- renders reports/<out>/dashboard.html from Phase 04/08/09/10/11's
already-generated JSON summaries (demand, forecast accuracy, discrepancies/
anomalies, monitoring, alerts/trackers). Same "generated, not hand-typed"
principle as every previous phase's report generator, aimed at a single
self-contained HTML page instead of Markdown.

Unlike every prior generator, this one must tolerate ANY of its five
inputs being unavailable: a person could run this phase having skipped an
earlier one, or (the situation in this sandbox) before real data exists at
all. A missing input renders an explicit "not yet available" placeholder
in that section -- never a fabricated number.

The output is intentionally a bare HTML fragment (a <title>, a <style>
block, then body content -- no <!DOCTYPE>/<html>/<head>/<body> wrapper).
HTML5's parser hoists <title>/<style>/<link> into an implicit <head> and
treats the rest as <body> even without those tags, so the file still opens
correctly in a plain browser; it is also exactly the shape the artifact
publishing contract this project's session used expects (it adds its own
skeleton). One file serves both without change.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE_FILES: dict[str, tuple[str, str]] = {
    "eda": ("phase04", "eda_summary.json"),
    "evaluation": ("phase08", "evaluation_summary.json"),
    "rca": ("phase09", "rca_summary.json"),
    "monitoring": ("phase10", "monitoring_snapshot.json"),
    "alerts": ("phase11", "alerts_and_tracker_summary.json"),
}

STATUS_LABELS = {"OK": "OK", "WARN": "Warning", "BREACH": "Breach", "UNKNOWN": "Unknown"}
MODEL_LABELS = {
    "naive": "Naive", "seasonal_naive": "Seasonal Naive",
    "ses": "SES", "croston": "Croston", "sba": "SBA", "lightgbm": "LightGBM",
}


def collect_inputs(reports_root: Path) -> dict[str, dict[str, Any] | None]:
    """Reads whichever of the five phase summaries exist under
    reports_root/phaseNN/filename.json -- a missing file is None, not an
    error, since this phase must render a partial dashboard gracefully."""
    inputs: dict[str, dict[str, Any] | None] = {}
    for key, (subdir, filename) in PHASE_FILES.items():
        path = reports_root / subdir / filename
        inputs[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return inputs


# --- small formatting helpers ------------------------------------------------


def _esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


def _model(name: str | None) -> str:
    if name is None:
        return "n/a"
    return MODEL_LABELS.get(name, name)


def _status_pill(status: str | None) -> str:
    status = status or "UNKNOWN"
    return f'<span class="pill pill-{status.lower()}">{_esc(STATUS_LABELS.get(status, status))}</span>'


def _empty(message: str) -> str:
    return f'<p class="empty">{_esc(message)}</p>'


def _bar_chart(items: list[tuple[str, float]], unit: str = "", width: int = 560) -> str:
    """A small, to-scale horizontal bar chart as inline SVG -- values drawn
    proportional to the largest one, labeled, theme-colored via CSS custom
    properties. No JS, no external chart library."""
    items = [(label, value) for label, value in items if value is not None]
    if not items:
        return _empty("No data.")
    max_value = max((v for _, v in items), default=0) or 1
    bar_height, gap, label_width, value_width = 24, 10, 132, 76
    chart_width = width - label_width - value_width
    height = len(items) * (bar_height + gap) + gap
    rows = []
    for i, (label, value) in enumerate(items):
        y = gap + i * (bar_height + gap)
        bar_w = max(2.0, (value / max_value) * chart_width)
        rows.append(
            f'<text x="{label_width - 10}" y="{y + bar_height * 0.68:.1f}" text-anchor="end" '
            f'class="bar-label">{_esc(label)}</text>'
            f'<rect x="{label_width}" y="{y}" width="{bar_w:.1f}" height="{bar_height}" rx="4" class="bar-fill" />'
            f'<text x="{label_width + bar_w + 8:.1f}" y="{y + bar_height * 0.68:.1f}" '
            f'class="bar-value">{value:,.3f}{_esc(unit)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" '
        f'aria-label="bar chart">' + "".join(rows) + "</svg>"
    )


# --- section builders --------------------------------------------------------


def _tile(value: str, label: str, tone: str = "") -> str:
    tone_class = f" tile-{tone}" if tone else ""
    return f'<div class="tile{tone_class}"><div class="tile-value">{value}</div><div class="tile-label">{_esc(label)}</div></div>'


def _render_at_a_glance(monitoring: dict | None, alerts: dict | None, evaluation: dict | None) -> str:
    overall_status = (monitoring or alerts or {}).get("overall_status")
    champion = (evaluation or monitoring or alerts or {}).get("champion_model")
    champion_wape = None
    if evaluation and champion:
        champion_wape = (evaluation.get("overall_by_model") or {}).get(champion, {}).get("wape")
    open_items = len((alerts or {}).get("open_tracker_items", [])) if alerts else None
    fired_alerts = len((alerts or {}).get("alerts", [])) if alerts else None

    tiles = [
        _tile(_status_pill(overall_status) if overall_status else "n/a", "Overall pipeline status",
              (overall_status or "unknown").lower()),
        _tile(_model(champion) if champion else "n/a", "Champion model"),
        _tile(_num(champion_wape) if champion_wape is not None else "n/a", "Champion overall WAPE"),
        _tile(str(fired_alerts) if fired_alerts is not None else "n/a", "Alerts fired this run"),
        _tile(str(open_items) if open_items is not None else "n/a", "Open tracker items"),
    ]
    return '<div class="tiles">' + "".join(tiles) + "</div>"


def _render_demand(eda: dict | None) -> str:
    if eda is None:
        return _empty("Phase 04 exploratory demand analysis has not been run yet.")

    trend = eda.get("trend", {})
    direction = trend.get("trend_direction", "n/a")
    slope = trend.get("ols_slope_per_day")

    categories = sorted(eda.get("categories", []), key=lambda r: r.get("total_unit_sales") or 0, reverse=True)[:6]
    cat_chart = _bar_chart([(f"{c['family']}" + (" (perishable)" if c.get("perishable") else ""),
                              c.get("total_unit_sales") or 0) for c in categories])

    hubs = sorted(eda.get("hubs", []), key=lambda r: r.get("total_unit_sales") or 0, reverse=True)[:6]
    hub_rows = "".join(
        f"<tr><td>Store {h['store_nbr']}</td><td>{_esc(h.get('store_type'))}</td>"
        f"<td>{_esc(h.get('city'))}</td><td>{_num(h.get('total_unit_sales'), 0)}</td></tr>"
        for h in hubs
    ) or '<tr><td colspan="4">No data.</td></tr>'

    sku = eda.get("sku", [])
    class_counts: dict[str, int] = {}
    for row in sku:
        cls = row.get("intermittency_class", "unclassified")
        class_counts[cls] = class_counts.get(cls, 0) + 1
    intermittency_chart = _bar_chart(list(class_counts.items()), unit=" items")

    promo = eda.get("promotion_effect", {})
    uplift = promo.get("uplift_pct_promoted_vs_not")

    pricing = eda.get("pricing", {})

    return f"""
    <div class="grid-2">
      <div class="card">
        <h3>Network demand trend</h3>
        <p class="stat-line"><strong>{_esc(direction)}</strong> ({_num(slope, 3)} units/day, OLS slope)</p>
        <h4>Top categories by volume</h4>
        {cat_chart}
      </div>
      <div class="card">
        <h3>Top hubs by volume</h3>
        <table><thead><tr><th>Hub</th><th>Type</th><th>City</th><th>Total units</th></tr></thead>
        <tbody>{hub_rows}</tbody></table>
        <h4>SKU intermittency mix</h4>
        {intermittency_chart}
      </div>
    </div>
    <p class="stat-line">Promotion uplift vs. non-promoted days: <strong>{_pct(uplift)}</strong>.
      Pricing dimension: <strong>{"analyzed" if pricing.get("analyzed") else "not available in this dataset"}</strong>.</p>
    """


def _render_forecast_accuracy(evaluation: dict | None) -> str:
    if evaluation is None:
        return _empty("Phase 08 forecast evaluation has not been run yet.")

    overall = evaluation.get("overall_by_model", {})
    champion = evaluation.get("champion_model")
    rows = "".join(
        f"<tr class=\"{'is-champion' if m == champion else ''}\"><td>{_esc(_model(m))}</td>"
        f"<td>{v.get('n')}</td><td>{_num(v.get('wape'))}</td><td>{_num(v.get('mae'))}</td>"
        f"<td>{_pct(v.get('forecast_bias'))}</td></tr>"
        for m, v in sorted(overall.items(), key=lambda kv: (kv[1].get("wape") is None, kv[1].get("wape") or 0))
    ) or '<tr><td colspan="5">No data.</td></tr>'

    by_family = (evaluation.get("by_dimension", {}) or {}).get("item_family", {})
    family_chart_items = []
    for family, by_model in by_family.items():
        wape = by_model.get(champion, {}).get("wape") if champion else None
        if wape is not None:
            family_chart_items.append((family, wape))
    family_chart = _bar_chart(sorted(family_chart_items, key=lambda kv: kv[1], reverse=True))

    return f"""
    <div class="card">
      <h3>Overall model comparison</h3>
      <p class="stat-line">Champion (lowest WAPE): <strong>{_esc(_model(champion))}</strong></p>
      <table><thead><tr><th>Model</th><th>n</th><th>WAPE</th><th>MAE</th><th>Bias</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>
    <div class="card">
      <h3>{_esc(_model(champion))}'s WAPE by category</h3>
      {family_chart}
    </div>
    """


def _render_discrepancies(rca: dict | None, eda: dict | None) -> str:
    if rca is None:
        return _empty("Phase 09 root-cause analysis has not been run yet.")

    data_issues = rca.get("data_issue_rca", [])
    discrepancies = rca.get("forecast_discrepancy_rca", [])
    explained = sum(1 for r in discrepancies if "cause unknown" not in r.get("statement", ""))
    unknown = len(discrepancies) - explained

    data_issue_items = "".join(
        f"<details><summary>{_esc(r['issue'].replace('_', ' ').title())} (n={r['n']})</summary>"
        f"<p>{_esc(r['statement'])}</p></details>"
        for r in data_issues
    ) or _empty("No data issues flagged.")

    discrepancy_items = "".join(
        f"<details><summary>{_esc(r['dimension'])} = {_esc(r['segment'])} "
        f"({'explained' if 'cause unknown' not in r.get('statement', '') else 'cause unknown'})</summary>"
        f"<p><em>{_esc(r['trigger_statement'])}</em></p><p>{_esc(r['statement'])}</p></details>"
        for r in discrepancies
    ) or _empty("No forecast discrepancies investigated.")

    anomalies = (eda or {}).get("network_anomalies", [])
    anomaly_rows = "".join(
        f"<tr><td>{_esc(a['date'])}</td><td>{_num(a.get('total_unit_sales'), 0)}</td><td>{_num(a.get('z_score'))}</td></tr>"
        for a in anomalies
    ) or '<tr><td colspan="3">No network-wide anomalies flagged.</td></tr>'

    return f"""
    <div class="grid-2">
      <div class="card">
        <h3>Data issues investigated</h3>
        {data_issue_items}
        <h3>Network-wide anomalies (Phase 04)</h3>
        <table><thead><tr><th>Date</th><th>Total units</th><th>z-score</th></tr></thead>
        <tbody>{anomaly_rows}</tbody></table>
      </div>
      <div class="card">
        <h3>Forecast discrepancies investigated</h3>
        <p class="stat-line"><strong>{explained}</strong> explained by available evidence,
           <strong>{unknown}</strong> cause unknown, of {len(discrepancies)} total.</p>
        {discrepancy_items}
      </div>
    </div>
    """


def _render_monitoring(monitoring: dict | None) -> str:
    if monitoring is None:
        return _empty("Phase 10 monitoring has not been run yet.")

    signals = monitoring.get("signals", [])
    cards = "".join(
        f'<div class="signal-card signal-{s["status"].lower()}">'
        f'<div class="signal-head"><span>{_esc(s["signal"].replace("_", " ").title())}</span>{_status_pill(s["status"])}</div>'
        f'<p>{_esc(s.get("reason", ""))}</p></div>'
        for s in signals
    ) or _empty("No signals recorded.")

    return f'<p class="stat-line">Overall status: {_status_pill(monitoring.get("overall_status"))}</p><div class="signals">{cards}</div>'


def _render_alerts(alerts: dict | None) -> str:
    if alerts is None:
        return _empty("Phase 11 alerts/tracker has not been run yet.")

    fired = alerts.get("alerts", [])
    alert_rows = "".join(
        f"<tr><td>{_esc(a['signal'])}</td><td>{_esc(a['previous_status'] or '(none)')} &rarr; {_esc(a['status'])}"
        f" ({_esc(a['direction'])})</td><td>{_esc(a['severity'])}</td></tr>"
        for a in fired
    ) or '<tr><td colspan="3">No alerts fired this run.</td></tr>'

    open_items = alerts.get("open_tracker_items", [])
    tracker_items = "".join(
        f"<details><summary>[{_esc(i['category'])}, {_esc(i['severity'])}] {_esc(i['description'])} "
        f"(seen {i['times_seen']}x)</summary>"
        f"<p>First seen: {_esc(i['first_seen_at'])} &middot; Last seen: {_esc(i['last_seen_at'])}</p></details>"
        for i in open_items
    ) or _empty("No open tracker items.")

    history = alerts.get("recent_history", [])
    history_chart = _bar_chart(
        [(f"Run {h['run_seq']}", {"OK": 0, "UNKNOWN": 1, "WARN": 2, "BREACH": 3}.get(h["overall_status"], 0) + 1)
         for h in history]
    )

    return f"""
    <div class="grid-2">
      <div class="card">
        <h3>Alerts fired this run</h3>
        <table><thead><tr><th>Signal</th><th>Transition</th><th>Severity</th></tr></thead>
        <tbody>{alert_rows}</tbody></table>
        <h4>Run history (severity rank, higher = worse)</h4>
        {history_chart}
      </div>
      <div class="card">
        <h3>Open discrepancy-tracker items</h3>
        {tracker_items}
      </div>
    </div>
    """


def _render_findings(evaluation: dict | None, rca: dict | None, alerts: dict | None) -> str:
    findings = []
    if evaluation:
        for f in evaluation.get("findings", []):
            findings.append((f.get("category", "finding"), f.get("recommendation", f.get("statement", ""))))
    if rca:
        for r in rca.get("forecast_discrepancy_rca", []):
            if "cause unknown" not in r.get("statement", ""):
                findings.append(("rca", f"{r['dimension']}={r['segment']}: {r['statement']}"))
    if alerts:
        for i in alerts.get("open_tracker_items", []):
            findings.append((i["category"], i["description"]))

    if not findings:
        return _empty("No actionable findings available yet.")

    items = "".join(
        f'<li><span class="finding-tag">{_esc(category)}</span> {_esc(text)}</li>'
        for category, text in findings
    )
    return f'<ul class="findings">{items}</ul>'


# --- top-level assembly -------------------------------------------------------


def render_dashboard(inputs: dict[str, dict[str, Any] | None], dataset_display_name: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    eda, evaluation, rca = inputs.get("eda"), inputs.get("evaluation"), inputs.get("rca")
    monitoring, alerts = inputs.get("monitoring"), inputs.get("alerts")

    all_missing = all(v is None for v in inputs.values())
    banner = (
        '<div class="banner">This dashboard is generated from the small synthetic fixture used throughout '
        "this project's sandbox (tests/fixtures/favorita_sample/) — never real Favorita data. "
        "See docs/phase_reports/phase14.md for why.</div>"
    )

    return f"""<title>DemandFlow Dashboard</title>
<style>
{_CSS}
</style>
{banner}
<header class="page-header">
  <div class="page-header-inner">
    <div>
      <h1>DemandFlow</h1>
      <p class="subtitle">{_esc(dataset_display_name)} — decision-oriented pipeline dashboard</p>
    </div>
    <nav>
      <a href="#demand">Demand</a>
      <a href="#accuracy">Accuracy</a>
      <a href="#discrepancies">Discrepancies</a>
      <a href="#monitoring">Monitoring</a>
      <a href="#alerts">Alerts</a>
      <a href="#findings">Findings</a>
    </nav>
  </div>
</header>
<main>
  <section class="at-a-glance">
    {_render_at_a_glance(monitoring, alerts, evaluation)}
  </section>

  <section id="demand">
    <h2>Demand</h2>
    {_render_demand(eda)}
  </section>

  <section id="accuracy">
    <h2>Forecast accuracy</h2>
    {_render_forecast_accuracy(evaluation)}
  </section>

  <section id="discrepancies">
    <h2>Discrepancies &amp; anomalies</h2>
    {_render_discrepancies(rca, eda)}
  </section>

  <section id="monitoring">
    <h2>Monitoring</h2>
    {_render_monitoring(monitoring)}
  </section>

  <section id="alerts">
    <h2>Alerts &amp; trackers</h2>
    {_render_alerts(alerts)}
  </section>

  <section id="findings">
    <h2>Actionable findings</h2>
    {_render_findings(evaluation, rca, alerts)}
  </section>
</main>
<footer>
  <p>Generated by <code>demandflow.reporting.generate_dashboard</code> at {_esc(generated_at)}.
  Do not hand-edit — re-run the pipeline and regenerate instead.{" No phase inputs were available for this run." if all_missing else ""}</p>
</footer>
"""


_CSS = """
:root {
  color-scheme: light;
  --bg: #EDF1F2;
  --surface: #FFFFFF;
  --ink: #16222A;
  --muted: #5B6B7A;
  --border: #D7DEE3;
  --accent: #1F6F78;
  --accent-ink: #FFFFFF;
  --ok: #2E7D53;
  --warn: #B7791F;
  --breach: #B3261E;
  --unknown: #6B7280;
  --font-display: "IBM Plex Sans", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #0F1620;
    --surface: #182430;
    --ink: #E7EDF0;
    --muted: #93A3AC;
    --border: #2B3947;
    --accent: #4FB3BD;
    --accent-ink: #0F1620;
    --ok: #4CAF7D;
    --warn: #D7A233;
    --breach: #E5534B;
    --unknown: #8A97A3;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0F1620;
  --surface: #182430;
  --ink: #E7EDF0;
  --muted: #93A3AC;
  --border: #2B3947;
  --accent: #4FB3BD;
  --accent-ink: #0F1620;
  --ok: #4CAF7D;
  --warn: #D7A233;
  --breach: #E5534B;
  --unknown: #8A97A3;
}
* { box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-display);
  margin: 0;
  padding-inline: 16px;
  font-variant-numeric: tabular-nums;
}
a { color: var(--accent); }
.banner {
  background: var(--accent); color: var(--accent-ink);
  font-size: 0.85rem; padding: 8px 16px; text-align: center;
  border-radius: 0 0 10px 10px; margin: 0 -16px 16px; max-width: calc(100% + 32px);
}
.page-header { position: sticky; top: env(safe-area-inset-top, 0px); background: var(--bg); z-index: 10; padding-block: 8px; border-bottom: 1px solid var(--border); }
.page-header-inner { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0; letter-spacing: -0.01em; }
.subtitle { margin: 2px 0 0; color: var(--muted); font-size: 0.9rem; }
nav { display: flex; flex-wrap: wrap; gap: 4px 14px; }
nav a { text-decoration: none; font-size: 0.88rem; font-weight: 600; }
main { max-width: 1100px; margin: 0 auto; padding-bottom: 40px; }
section { scroll-margin-top: 64px; padding-block: 28px; border-bottom: 1px solid var(--border); }
section:last-of-type { border-bottom: none; }
h2 { font-size: 1.15rem; margin: 0 0 14px; }
h3 { font-size: 1rem; margin: 0 0 8px; }
h4 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 18px 0 8px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; padding-block: 20px 4px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile-value { font-family: var(--font-mono); font-size: 1.4rem; font-weight: 600; }
.tile-label { color: var(--muted); font-size: 0.78rem; margin-top: 4px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); font-family: var(--font-mono); }
th { font-family: var(--font-display); color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; }
tr.is-champion td { font-weight: 700; color: var(--accent); }
.stat-line { font-size: 0.92rem; }
.empty { color: var(--muted); font-style: italic; font-size: 0.9rem; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; font-family: var(--font-mono); }
.pill-ok { background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }
.pill-warn { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
.pill-breach { background: color-mix(in srgb, var(--breach) 18%, transparent); color: var(--breach); }
.pill-unknown { background: color-mix(in srgb, var(--unknown) 18%, transparent); color: var(--unknown); }
.tile-ok .tile-value { color: var(--ok); }
.tile-warn .tile-value { color: var(--warn); }
.tile-breach .tile-value { color: var(--breach); }
.tile-unknown .tile-value { color: var(--unknown); }
.signals { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.signal-card { border: 1px solid var(--border); border-left-width: 4px; border-radius: 8px; padding: 12px 14px; background: var(--surface); font-size: 0.88rem; }
.signal-ok { border-left-color: var(--ok); }
.signal-warn { border-left-color: var(--warn); }
.signal-breach { border-left-color: var(--breach); }
.signal-unknown { border-left-color: var(--unknown); }
.signal-head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; margin-bottom: 6px; }
.bar-label, .bar-value { font-family: var(--font-mono); font-size: 12px; fill: var(--ink); }
.bar-value { fill: var(--muted); }
.bar-fill { fill: var(--accent); }
details { border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; font-size: 0.88rem; background: var(--surface); }
details summary { cursor: pointer; font-weight: 600; }
details p { margin: 8px 0 0; color: var(--muted); }
.findings { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.findings li { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; }
.finding-tag { display: inline-block; font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 1px 6px; margin-right: 8px; }
footer { max-width: 1100px; margin: 0 auto; padding: 20px 0 40px; color: var(--muted); font-size: 0.8rem; }
svg { display: block; overflow: visible; }
table { overflow-x: auto; display: block; }
@media (max-width: 480px) {
  .page-header-inner { flex-direction: column; align-items: flex-start; }
}
"""


def generate_and_write(reports_root: Path, out_path: Path, dataset_display_name: str) -> Path:
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, dataset_display_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _main() -> None:
    from demandflow.config import load_config

    cfg = load_config()
    out_path = Path("docs") / "dashboard.html"
    generate_and_write(cfg.paths.reports_dir, out_path, cfg.dataset.display_name)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    _main()
