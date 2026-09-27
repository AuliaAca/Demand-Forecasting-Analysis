# Phase 14 — Looker Studio / Dashboard: Review Package

**Phase objective (from the Phase 14 prompt):** build a decision-oriented
dashboard aligned with the JD's dashboards requirement. Show relevant
demand, forecast accuracy, discrepancies/anomalies, monitoring,
alerts/trackers, and actionable findings where supported.

**Status: a real, self-contained, interactive HTML dashboard, generated
from real fixture-pipeline output and rendered end to end in this
session. Not Looker Studio — see "Why not Looker Studio" below for the
justification, which is a project decision, not a silent substitution.**

---

## Why not Looker Studio

CLAUDE.md §3.4 is explicit: *"The exact implementation technology is not
specified for these four items [datasets, dashboards, trackers, alerts]
... Choose technology based on usefulness, cost, and project scope."*
Looker Studio is named only as a bonus *exposure* signal (§5), not a
requirement, and the phase's own title ("Looker Studio / Dashboard")
already frames it as one option for the real deliverable, the dashboard
itself.

Looker Studio specifically requires a Google account and an interactive
browser-based OAuth flow to even create a report, and a real data source
(BigQuery, ideally — but Phase 13's BigQuery port has never run against a
live project either, for the same disclosed reason). Neither is available
in this sandbox: there is no way to authenticate interactively here, and
there is no live data source to point it at. Building one would mean
either fabricating a connection that was never actually exercised, or
producing a document that only *describes* what a Looker Studio report
would contain — exactly the kind of unverified claim CLAUDE.md §19 rules
out.

Instead, this phase builds a real, running dashboard using free, local,
already-available tools: Python (already this project's language) to
generate a single self-contained HTML file from the JSON summaries Phases
04/08/09/10/11 already produce. It was actually rendered, actually
inspected, and is actually usable — offline, in any browser, no account
required. This is squarely inside CLAUDE.md §9's cost principle: prefer
free/local solutions that demonstrate the required capability over cloud
tooling that would add cost and risk without adding evidence here.

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/reporting/generate_dashboard.py` | `collect_inputs()` reads whichever of Phase 04/08/09/10/11's JSON summaries exist (a missing one renders an explicit "not yet available" placeholder, never a fabricated number); `render_dashboard()` builds the page; small pure functions per section (`_render_demand`, `_render_forecast_accuracy`, `_render_discrepancies`, `_render_monitoring`, `_render_alerts`, `_render_findings`) plus a dependency-free inline-SVG bar-chart helper (`_bar_chart`) — no JS charting library, no CDN dependency. |
| `tests/unit/test_generate_dashboard.py` | 12 tests, including a real HTML tag-balance checker (built on `html.parser.HTMLParser`) that would catch a stray unclosed `<div>` from the many f-strings this generator is assembled from — not just "does it run without error." |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to 26 steps (step 26). New target: `make dashboard` / `make phase14`. |

**Total test count: 326 passed + 1 skipped** (up from 314 + 1 — the
skipped test is still Phase 12's Airflow-only file).

### The six required sections, mapped to real data

| Objective's category | Section | Data source |
|---|---|---|
| Demand | `#demand` | Phase 04: network trend, top categories/hubs by volume, SKU intermittency mix, promotion uplift |
| Forecast accuracy | `#accuracy` | Phase 08: overall model comparison (WAPE/MAE/bias), champion model's WAPE by category |
| Discrepancies / anomalies | `#discrepancies` | Phase 09: data-issue and forecast-discrepancy RCA (explained vs. "cause unknown"); Phase 04: network-wide anomalies |
| Monitoring | `#monitoring` | Phase 10: all four signals (accuracy, deterioration, data quality, anomalies) with status and reason |
| Alerts / trackers | `#alerts` | Phase 11: alerts fired this run, run-history severity trend, open discrepancy-tracker items |
| Actionable findings | `#findings` | Phase 08 finding recommendations, Phase 09 explained-discrepancy statements, Phase 11 open tracker items |

At-a-glance tiles above all six sections surface the headline numbers
(overall pipeline status, champion model, champion WAPE, alerts fired,
open tracker items) — "put the summary before the detail," since a
dashboard is scanned and operated, not read top to bottom.

---

## Real numbers, actually rendered

The dashboard was generated from a real, full run of Phases 01–11 against
the fixture in this session (build the warehouse, run EDA, evaluation,
RCA, monitoring, alerts) and inspected directly — not just asserted to
work. What it actually shows on that run:

- **Overall status: Breach**, champion model **Seasonal Naive** (WAPE
  0.908) — matching Phase 08/10's own hand-verified numbers exactly.
- **Demand**: increasing network trend (+0.727 units/day), DAIRY the
  top category by volume, Store 2 the top hub.
- **Forecast accuracy**: the full 5-model comparison table, Seasonal
  Naive's WAPE by category (PRODUCE 1.000, DAIRY 0.964, GROCERY 0.836).
- **Discrepancies**: 1 return and 1 extreme-value row investigated (both
  "cause unknown" at this sample size); of 14 forecast discrepancies, the
  explained/unknown split from Phase 09's own findings.
- **Monitoring**: all four signals with their real reasons, e.g. *"Worst
  DQ rule severity observed maps to BREACH: grain_duplicates,
  orphan_dimension_keys."*
- **Alerts**: the 2 alerts that fired on the first recorded run
  (data_quality → BREACH, anomalies → WARN), 4 open tracker items.
- **Findings**: the concrete recommendation text from Phase 08's
  systematic-bias findings (e.g. *"Flag item_family=DAIRY for manual
  review before relying on this model's forecast there"*).

Every one of these numbers is copied from a real run in this session, the
same discipline as every previous phase's review package.

---

## Real validation, not just "it renders"

1. **Ran the actual pipeline** (Phases 01–11 against the fixture) and
   generated the dashboard from real output, inspected directly (not a
   hand-built fixture summary).
2. **Parsed the output with Python's own `html.parser`** to confirm every
   opened tag is properly closed — a real, structural correctness check
   for markup assembled from many f-strings, where an unclosed `<div>` is
   an easy, real mistake to make (and did happen once during development —
   see "A real bug" below).
3. **Checked HTML-escaping directly**: monitoring reasons contain literal
   `>=` characters (e.g. "WARN >= 1.0"); confirmed these render as `&gt;=`
   in the output, not raw, unescaped text.
4. **Checked the SVG bar charts are proportionally scaled**: extracted
   every `<rect>` width from the rendered output and confirmed they are
   all positive and scale correctly relative to the largest value in each
   chart, not just "an SVG element exists somewhere."
5. **Confirmed graceful degradation**: rendered the page with all five
   inputs missing, and with a partial mix (some present, some missing) —
   each missing section shows its own explicit placeholder text, and every
   present section still renders correctly regardless of which others are
   missing.

### A real bug, caught by the tag-balance check

The test file's own tag-balance checker initially flagged 9 "mismatched
close tag: 'rect'" errors — not a bug in the generated dashboard (already
confirmed well-formed by a separate ad hoc check earlier in this session),
but a bug in the *test's* `HTMLParser` subclass: it skipped pushing
self-closing void elements (like `<rect ... />`) onto its tag stack, but
didn't also skip the automatic `handle_endtag` call Python's parser fires
for them, so every self-closed SVG `<rect>` looked like an unmatched
closing tag. Fixed by having the checker ignore `handle_endtag` calls for
void elements too, consistent with how it already skips them on open —
now correctly reports zero errors, and would catch a genuine mismatch
elsewhere in the page.

---

## Why this is still validated on the fixture, not real data

Unchanged mechanism from Phases 01–13: no Kaggle network access in this
sandbox, so the dashboard was generated from the same small committed
fixture every other phase uses. The dashboard's own top banner says so
explicitly, in the page itself — not just in this review package — so
anyone who opens the file (or a link to it) sees the disclosure before
anything else, exactly the same honesty standard as every `_PREVIEW.md`
report this project has generated since Phase 01.

### To generate the real dashboard

```bash
# after make phase01 through phase11 have produced real reports/phaseNN/*.json:
make dashboard   # writes docs/dashboard.html
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"Build automated ... dashboards ... to make planning faster and smarter"** — this phase's literal mission | Position missions; CLAUDE.md §3.4 |
| **A single view connecting demand, accuracy, discrepancies, monitoring, alerts, and recommendations** — exactly this phase's objective, and the natural endpoint of the forecast → evaluation → monitoring → finding → recommendation chain CLAUDE.md §3.3 describes | This phase's own objective line; CLAUDE.md §3.3 |
| **"Looker Studio" bonus exposure evaluated, not defaulted to** — a documented, justified decision not to use it, per CLAUDE.md §9's cost principle, rather than a silent substitution | CLAUDE.md §5 |
| **Reused, not duplicated, five earlier phases' work** — every number on the dashboard comes from an existing JSON summary; nothing was recomputed | CLAUDE.md engineering principles |

Not yet covered: nothing remains in the explicit phase list beyond
Phase 16 (Portfolio Polish & Final Audit) and Phase 15 (Testing &
Reliability).

---

## Key decisions

- **Not Looker Studio** — justified above, matching this phase's own
  conditional framing ("Looker Studio / Dashboard," not "Looker Studio").
- **One self-contained HTML file, no build step, no JS framework, no CDN
  dependency.** Charts are hand-drawn inline SVG from Python, not a
  charting library — the same cost-conscious, dependency-minimal instinct
  as every other phase's technology choice.
- **The file is a bare HTML fragment** (`<title>`, `<style>`, body content
  — no `<!DOCTYPE>`/`<html>`/`<head>`/`<body>` wrapper). HTML5's
  error-tolerant parser hoists `<title>`/`<style>` into an implicit
  `<head>` and treats the rest as `<body>` even without those tags, so the
  file opens correctly in a plain browser either way — this shape was
  chosen deliberately so the same file works when opened directly and when
  published through a hosted-artifact viewer with its own skeleton,
  without needing two versions.
- **Missing inputs degrade gracefully, per-section**, rather than the
  whole page failing or fabricating placeholder numbers — necessary
  because this sandbox may run Phase 14 with some or all of Phases
  04/08/09/10/11's real output unavailable.
- **The disclosure banner lives in the page itself**, not only in this
  review package — a dashboard is the kind of artifact that could be
  opened or shared independently of the chat it was produced in.

## Validation

```
$ python3 -m pytest tests/ -q
........................................................................ [ 22%]
........................................................................ [ 44%]
........................................................................ [ 66%]
........................................................................ [ 88%]
......................................                                   [100%]
326 passed, 1 skipped in 175.37s

$ make smoke   # 26 steps, ending with the Phase 14 dashboard
...
[26/26] Rendering the decision-oriented dashboard (fixture preview — NOT the real dashboard)
       wrote .../reports/fixture_smoke_test/dashboard_PREVIEW.html
Smoke test complete.
```

Both commands were actually run in this session; every number in this
document is copied from that real output, then cleaned up
(`make clean-smoke`; git-ignored anyway).

## Findings

- **No findings about the real dataset** — this phase assembles and
  presents, it doesn't compute anything new.
- **The dashboard surfaces Phase 10's headline finding front and center**:
  the overall status tile reads BREACH at a glance, not buried in a
  report a reader has to scroll through — exactly the "decision-oriented"
  requirement in practice.
- **A real bug was caught by the HTML well-formedness test**, in the
  test's own checker rather than the generated markup — still evidence
  the validation approach works as intended (see above).

## Limitations

- **Never rendered in an actual browser in this session** (no GUI
  available) — validated via `html.parser`-based structural checks,
  direct text-content inspection, and SVG geometry checks instead. Visual
  rendering should still be spot-checked by a human before treating this
  as final.
- **Not Looker Studio, and not connected to BigQuery** — a documented
  scope decision (see above), not an oversight; if real GCP/Looker Studio
  access becomes available later, the JSON summaries this dashboard
  already consumes are the natural data source for a real Looker Studio
  report built on top of Phase 13's BigQuery tables.
- **All earlier phases' limitations still apply unchanged**, and this
  dashboard inherits every one of them since it only displays their
  output (fixture-only validation, no pricing dimension, store-as-hub
  proxy, small-sample RCA/monitoring caveats already documented in their
  own review packages).

## What to review

1. **Open the generated dashboard in a real browser** (`make dashboard`
   after running Phases 01–11, or open the file this review package's
   companion artifact link renders) and confirm it looks right visually —
   this phase's own validation could not do that step.
2. **The "not Looker Studio" justification** — confirm you're comfortable
   with this scope decision given the sandbox's real constraints.
3. **Whether the six sections and the at-a-glance tiles surface the right
   headline numbers** for an actual planning decision, versus what you'd
   want moved, added, or removed.
4. **Run `make phase01` through `make dashboard` locally** once Kaggle
   access exists, to see the real dashboard against real data.

## Interview questions

- Why wasn't Looker Studio used here, and what specifically about this
  sandbox made that the right call rather than a shortcut?
- Walk through how the dashboard degrades when one or more of its five
  JSON inputs is missing — what does the page show, and why does that
  matter for a phase that could run before earlier phases have real data?
- Why is the dashboard file authored without an `<html>`/`<head>`/`<body>`
  wrapper, and why does it still open correctly in a plain browser?
- What did the HTML tag-balance test actually catch, and why was the bug
  in the test's own logic rather than the dashboard's generated markup —
  what does that distinction tell you about how to read a "test failure"?
- If this dashboard needed to become a live, auto-refreshing view instead
  of a point-in-time snapshot, what would have to change, and what
  wouldn't?
- How would you extend this dashboard once BigQuery (Phase 13) and
  Airflow (Phase 12) are both running for real, rather than validated
  offline?

---

**STOP — Phase 14 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 15 (Testing & Reliability) has not
started.
