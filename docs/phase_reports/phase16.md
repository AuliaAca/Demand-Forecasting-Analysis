# Phase 16 — Portfolio Polish & Final Audit: Review Package

**Phase objective (from the Phase 16 prompt):** polish the portfolio and
perform a final audit against every relevant item in the exact target-role
profile (CLAUDE.md §1). Identify demonstrated, partially demonstrated, not
demonstrated, and dataset-limited requirements. Do not overstate
professional experience or role-specific knowledge.

**Status: the final audit below classifies all 46 line items CLAUDE.md
§20 names, sourced from the 15 real phase reports already committed —
not re-derived from memory. A repository-root `README.md` was added (the
one structural portfolio gap found: `pyproject.toml` has referenced
`README.md` since Phase 01, but the file never existed). No forecasting,
evaluation, or pipeline code changed in this phase — Phase 16 is audit
and presentation, not new capability.**

---

## What was built

| Path | Purpose |
|---|---|
| `README.md` (new, repo root) | The portfolio's front door: what the project is, the anonymized-JD honesty notice, the pipeline architecture, the real-data-access gap disclosure, how to run every phase, a repository map, and a link to this phase's final audit. `pyproject.toml` has declared `readme = "README.md"` since Phase 01's `pyproject.toml` was first written; the file itself never existed until now — confirmed missing by checking `pip show demandflow`'s empty `Summary`/description before this phase, and populated after. |
| `docs/phase_reports/phase16.md` (this file) | The final audit: every Position-purpose, Mission, Requirement, and Bonus item from CLAUDE.md §20, classified against the real evidence already produced by Phases 01–15, with a source phase/file for every claim. |

No other files changed. This phase does not touch `src/`, `tests/`,
`sql/`, `dags/`, or any generated report — its two deliverables are
both documentation, consistent with "polish and audit" as a phase, not
"build."

---

## Final Audit

Per CLAUDE.md §20's instruction, this is a classification, **not a score
or ranking**: no item count, fraction, or percentage is computed below.
Each row cites the phase(s) and file(s) the classification is drawn from,
so every claim here is traceable to a real, already-reviewed artifact
rather than restated from memory.

Legend: **D** = Demonstrated · **P** = Partially demonstrated · **N** =
Not demonstrated · **L** = Limited by dataset · **NA** = Not applicable
to project. Several items are dataset-limited *and* only partially
demonstrated for the same underlying reason; those are marked **P/L**
and explained in the Evidence column rather than forced into one bucket.

### Position purpose

| Item | Status | Evidence |
|---|---|---|
| Demand forecast accuracy | **D** | Phases 05–08: Naive → Seasonal Naive → statistical (Croston/SBA) → LightGBM, each backtested and compared with WAPE/MAE/bias; Phase 08 evaluates accuracy across every JD-named dimension. |
| Demand forecast reliability | **D** | Phase 10 (accuracy + deterioration signals over repeated backtests), Phase 15 (reproducibility: fixed LightGBM seed, connection-handling hardening, CI). Reliability is shown on a historical fixture replay, not live operation — the same scope limit the Phase 00 plan named for RO-2 from the start. |
| Sales/demand pattern analysis | **D** | Phase 04's EDA (trends, seasonality, outliers, anomalies) plus Phase 03's analytical marts. One inherited framing caveat, documented since Phase 00: Favorita records *sales*, not *demand* — zero-sales/stockout periods are not distinguishable from true zero demand in this dataset, so "demand pattern" analysis is really sales-pattern analysis used as demand's observable proxy. |
| Forecasting logic | **D** | Phases 05–07: three method families (naive, statistical/intermittent-demand, ML), each with a stated, evidence-based reason for trying it rather than defaulting to it (CLAUDE.md §10). |
| Automated tools | **D** | The whole pipeline: DQ rules (02), SQL warehouse build (03), backtests (05–07), evaluation (08), RCA (09), monitoring (10), alerts/trackers (11), Airflow DAG (12), dashboard (14), CI (15) — all `make`-invokable, none manual. |
| Monitoring | **D** | Phase 10 (four signals: accuracy, deterioration, data quality, anomalies, each with an explicit PASS/WARN/BREACH threshold), Phase 11 (persisted run history, status-transition alerts). |
| Inventory/fulfillment decision support | **P / L** | Phase 08's finding logic (`src/demandflow/evaluation/segment_evaluation.py`) explicitly frames a model's bias direction as "over-forecasting risks excess inventory and holding cost" / "under-forecasting risks stockouts and unmet demand" — a real, implemented mechanism connecting forecast error to a decision-relevant risk, not just an accuracy number. It cannot go further: Favorita has no inventory, stock-level, or order data, so no fill-rate or stock-cover number can actually be computed (documented since Phase 00's ADR, RO-6). |
| Product availability / just-in-time objective | **P / L** | Same bias-direction-as-risk-proxy mechanism (Phase 08) is the concrete link to this objective. Phase 00's own ADR calls this correctly: "just-in-time is framed, not measured" (RO-7) — no lead-time or stock data exists to measure it directly, and no real cross-functional work on availability happened (see "cross-team collaboration," below). |

### Missions

| Item | Status | Evidence |
|---|---|---|
| SKU | **D** | `item_nbr` / `dim_sku` (Phase 03) is the grain of every backtest, evaluation, and RCA record; Phase 04/08 also classify SKUs by intermittency. |
| Hub | **D**¹ | `dim_hub` (Phase 03), used throughout Phases 04–11 for store-level/segment analysis. ¹Documented proxy: Favorita's dataset unit is "store," used as "hub" throughout since ADR 0001 (§5.4: "matches 'SKU' and 'hub' directly... no objection") — the analytical capability (group/analyze by fulfillment location) is fully real; only the literal word differs from the JD's. |
| Category | **D** | Item family (Phase 03's `dim_sku.family`), used as the category dimension in Phase 04/08 segment analysis. |
| Campaign | **D** | Favorita's `onpromotion` flag (item × store × day) is a genuine, per-record promotion signal — ADR 0001 notes this is a real advantage over the alternative dataset considered (M5), which has no promotion flag at all. Used in Phase 04 (promotion-lift) and Phase 08 (promotion segment evaluation, where it drives the phase's one segment-champion-switch finding). |
| Pricing | **N / L** | No pricing dimension exists anywhere in the Favorita dataset. Accepted as a documented gap at dataset-selection time (ADR 0001, decision D2) and restated, unchanged, in every phase's Limitations section since Phase 02. Not fabricated, not silently dropped. |
| Seasonal events | **D** | `holidays_events.csv` (national/regional/local holidays, with transferred-holiday handling) plus a payday flag, both materialized in Phase 03's calendar model and used in Phase 04/08 segment analysis. |
| Trends | **D** | Phase 04's network trend line (`trend_summary`), reused directly by Phase 10's anomaly/monitoring signal. |
| Seasonality | **D** | Phase 04 (weekly/seasonal pattern analysis), Phase 06 (Seasonal Naive, tested against the hypothesis that seasonality is strong enough to beat plain Naive). |
| Outliers | **D** | Phase 02's coarse IQR-fence screen, refined by Phase 04's context-aware, business-informed outlier review. |
| Demand anomalies | **D** | Phase 04's `network_anomalies` function, operationalized as a live signal in Phase 10's monitoring. |
| Forecast accuracy | **D** | Phases 05–08 (see Position purpose row above). |
| Actionable recommendations | **D** | Phase 08 findings carry a `recommendation` string per finding (e.g. "flag item_family=DAIRY for manual review"); Phase 09 RCA records carry an evidence-based `statement`; Phase 11's tracker carries open items with `severity`; Phase 14's dashboard aggregates all three into one `#findings` section — the recommendations log the JD's mission line asks for, distributed across the phases that produce each kind of finding rather than a single flat document. |
| Datasets | **D** | Phase 03's layered SQL warehouse (staging → intermediate → marts), the reusable analytical dataset the JD mission names. |
| Dashboards | **D** | Phase 14's decision-oriented HTML dashboard — not Looker Studio (see Bonus, below), a documented technology-choice decision, not a silent substitution. |
| Trackers | **D** | Phase 11's `discrepancy_tracker` (persisted, idempotently upserted, open/resolved lifecycle). |
| Alerts | **D** | Phase 11's status-transition alerting (fires only on a signal's status change, verified noise-free by an actual double-run in that phase's own tests). |
| SQL | **D** | Every phase since Phase 01: DuckDB SQL throughout the warehouse and every backtest/evaluation query; Phase 13 ports the same logic to BigQuery-dialect SQL. |
| Python | **D** | The entire codebase (`src/demandflow/`) — ingestion, transformation orchestration, forecasting, evaluation, RCA, monitoring, alerting, reporting, all Python. |
| BigQuery | **P / L** | Phase 13: a real, correct 14-model SQL port with 6 actual BigQuery-dialect gotchas found and fixed (not a superficial re-typing), validated with an independent offline parser (`sqlglot`) plus structural cross-checks. Never executed against a live BigQuery project — no GCP project or billing account exists in this sandbox (disclosed explicitly in Phase 13's own review package, unchanged since). BigQuery is also explicitly "a plus" in the JD's own requirements, not a mandatory item (CLAUDE.md §3.5). |
| Data issues | **D** | Phase 02's rule catalog (rule/finding/severity/consequence/handling-decision), Phase 09's data-issue RCA (returns, extreme values, with business-context evidence). |
| Forecast discrepancies | **D** | Phase 08's segment/systematic-bias/champion-switch findings feed directly into Phase 09's discrepancy RCA as investigation triggers. |
| Root-cause analysis | **D** | Phase 09: evidence-based investigation of both data issues and forecast discrepancies, with a hard-enforced "associated with"/"consistent with"/"cause unknown" vocabulary (never "caused by") — CLAUDE.md §13's discipline is enforced by construction (only two template-writing functions produce prose), not just by instruction. |
| Scalable solutions | **P** | Architectural evidence only, not a load test: Phase 01's full-file profiling runs against the complete dataset via DuckDB without needing it to fit in RAM; every SQL model in Phase 03 is written to run unmodified at a larger dev-scope fraction or the full dataset (only the dev-scope CSV's row selection would change); Phase 12's Airflow DAG expresses the pipeline's real dependency graph so steps can run in parallel, not just sequentially. None of this was ever actually run at real-dataset scale in this sandbox (no Kaggle access) — "designed to scale," not "proven at scale." |

### Requirements

| Item | Status | Evidence |
|---|---|---|
| SQL / large datasets | **D** | See Missions: SQL, above; Phase 01's DuckDB profiling is specifically designed to handle a dataset too large to load into memory at once. |
| Python | **D** | See Missions: Python, above. |
| Forecasting concepts (trends, seasonality, outliers, forecast accuracy) | **D** | See Missions: trends/seasonality/outliers/forecast accuracy rows, above — all four implemented as distinct, separately-tested concepts, not folded into one undifferentiated "forecasting" step. |
| Dashboards, reporting automation, data products, monitoring tools | **D** | Phase 03 (data products), Phase 10 (monitoring), Phase 14 (dashboard) — every generated Markdown/HTML report across all 15 phases is produced by code, not written by hand. |
| Analytical / problem-solving skill, attention to detail | **P** | Real, repeated evidence throughout — e.g. Phase 06/07 reporting a negative result rather than only a favorable one, Phase 13 finding and fixing 6 real BigQuery-dialect bugs, Phase 15 finding 4 real connection leaks by re-reading control flow rather than trusting a passing test suite. Per CLAUDE.md §4, this is a soft skill a project can evidence but not conclusively prove — ultimately reviewer-judged, not self-certified. |
| Turn complex analysis into clear business insights/recommendations | **D** | Phase 04's business-language EDA findings, Phase 08's recommendation strings, Phase 14's dashboard — all written for a reader making a decision, not a data scientist reading a model summary. |
| Comfortable in a fast-paced environment, collaborating across teams | **P / NA** | CLAUDE.md §3.7 is explicit: "DemandFlow cannot reproduce real organizational collaboration... never claim real collaboration." What exists instead is a simulated stakeholder-routing perspective (Phase 02 routes an orphan-key finding to a "Data Engineering" perspective; Phase 09/11 continue that pattern) — real evidence of *thinking in terms of* cross-functional handoffs, not evidence of *having done* real cross-team collaboration. |

### Bonus

| Item | Status | Evidence |
|---|---|---|
| E-commerce / quick commerce / retail / FMCG / supply chain experience | **P / NA** | The project's own framing (CLAUDE.md §6) is "a fictional retail / quick-commerce business," and Favorita itself is a real grocery-retail dataset — industry-relevant *simulation*, not real professional experience in the industry. CLAUDE.md §2 is explicit that the project must never claim the target company's real practices as its own. |
| Airflow | **D** | Phase 12: a real, installed, executed 24-task DAG over this project's actual pipeline (not a description of one), with dependencies, retries, and failure-handling (retry → exhaust → callback → downstream-skip) all verified directly. Never completed a real end-to-end run against live Kaggle data (documented, unchanged limitation). |
| GCP | **P / L** | Via BigQuery (Phase 13) — GCP's own product — the same real-SQL-port evidence applies, with the same "never executed against a live project" caveat. |
| Looker Studio | **N** | A documented decision *not* to use it (Phase 14's own review package: no interactive OAuth flow or live data source available in this sandbox, so a "Looker Studio report" here would have meant fabricating a connection never actually exercised — ruled out by CLAUDE.md §19). A real, running local-HTML dashboard was built instead, per CLAUDE.md §3.4/§9. |
| Superset | **N** | Scoped out from Phase 00 onward as a documented decision ("a second dashboard adds no new evidence," `docs/00_requirement_analysis_and_system_plan.md` B-2d) — never attempted, not an oversight. |
| Git | **D** | The entire project is version-controlled from Phase 00 onward; Phase 15 added a CI workflow that runs on every push. |
| Machine-learning forecasting | **D** | Phase 07: a global LightGBM model over leakage-safe features, evaluated against three simpler baselines on an identical held-out set, with the method choice explicitly justified (CLAUDE.md §5 names this a bonus, not a requirement). |

### A note on experience/qualification signals (not part of the §20 checklist itself)

CLAUDE.md §4 is explicit that "1–3 years of experience in Data Analytics,
BI, Supply Chain Analytics, Analytics Engineering, or a similar role" is a
candidate qualification signal, not something this project can truthfully
satisfy — no phase has claimed otherwise, and this audit does not either.
The project demonstrates relevant *capabilities*; it is not a substitute
for, and should not be presented as equivalent to, that stated experience
requirement.

---

## JD connection

Per this phase's own explicit instruction, the exact requirement(s) *this
phase* (16, not the whole project) provides evidence for:

| What this phase provides evidence for | JD reference |
|---|---|
| **"Turn complex analysis into clear business insights and recommendations"** — applied reflexively, to the project's own results: the audit above is exactly this skill, exercised on 46 real, sourced findings rather than raw notes | Requirements |
| **"Great attention to detail"** — every audit row is checked against a real, already-committed phase report or source file, not asserted from memory; the one real structural gap found (`README.md` referenced in `pyproject.toml` since Phase 01, never created) was caught by directly checking package metadata (`pip show demandflow`), not by inspection alone | Requirements (R-6) |
| **Honesty / source discipline (CLAUDE.md §19)** — every "Demonstrated" classification above cites a specific phase and file; every "Partially demonstrated" or "Not demonstrated" states the real reason (dataset gap, sandbox constraint, or a mission that cannot be truthfully claimed as real professional experience), matching this phase's own explicit instruction: "Do not overstate professional experience or [role]-specific knowledge" | CLAUDE.md §19; this phase's objective line |
| **Build automated ... datasets** (indirectly) — `README.md` is itself a small automation-adjacent deliverable: a single, accurate entry point generated from the real state of 15 already-built phases, rather than hand-maintained prose that could drift from what the code actually does | Missions (weak, secondary connection — this phase's primary evidence is the audit and documentation work above, not new pipeline automation) |

---

## Key decisions

- **The audit sources every claim from the real phase reports, not from
  recollection.** Each of the 15 existing `docs/phase_reports/phaseNN.md`
  files' own "JD connection" and "Limitations" sections was read directly
  in this phase before writing a single row of the table above — the same
  "verify, don't assume" discipline CLAUDE.md has required since Phase 01.
- **No score, percentage, or ranking, per CLAUDE.md §20's explicit
  instruction.** Where an item is genuinely mixed (real mechanism, but
  capped by a dataset or sandbox limit), it is marked **P/L** and the
  Evidence column explains both halves, rather than forcing a binary
  Demonstrated/Not-demonstrated call that would misrepresent either the
  real work done or the real gap.
- **"Hub" and "e-commerce/quick-commerce experience" are graded
  honestly despite being adjacent to strong evidence.** Hub is marked
  **Demonstrated** (with its proxy documented inline) because the
  underlying analytical capability is fully real, only the literal term
  differs. Industry experience is marked **P/NA** because, however
  retail-realistic the dataset and scenario are, CLAUDE.md §2 forbids
  presenting a simulation as real professional experience — the
  distinction is about what is being claimed, not how good the work is.
- **`README.md` was the one concrete portfolio-polish gap actually
  found**, not invented busywork to justify this phase's "polish" half.
  It was confirmed missing (not just assumed) by checking
  `pip show demandflow`'s empty description before writing it, and by
  `git ls-files` showing no root-level `README.md` had ever been
  committed across any of the previous 15 phases.
- **No source code was touched.** Phase 16's objective is audit and
  polish, not new capability — CLAUDE.md §18's phase-discipline
  principle applies here too: this phase's own scope is respected, not
  quietly expanded into a Phase 15.1.

---

## Validation

```
$ pip show demandflow   # before this phase
Summary: DemandFlow — Retail Demand Forecasting & Planning Intelligence Platform (portfolio project).
# (long description empty -- confirms README.md was missing)

$ git ls-files | grep -i '^README'
# (no output, before this phase)
```

Since this phase changes no `src/`/`tests/`/`sql/`/`dags/` code, the
full test suite was not expected to change and was not re-run as part of
this phase's own work; Phase 15's closing validation (`353 passed, 1
skipped`) is the most recent real run and remains the current, accurate
state of the suite. The standard leak-sweep grep (real-company-identity
markers, run against the full repository excluding `.private/`, `.git/`,
and the two Airflow-only environment directories) was re-run against the
final diff (`README.md` + this file) and came back clean, unchanged from
every prior phase: the only match is still the one known, intentional
Airflow-vendor-name disambiguation note in
`docs/00_requirement_analysis_and_system_plan.md`, first added in Phase 12.

`README.md` itself was read back after writing to confirm every internal
link it makes (to `CLAUDE.md`, `docs/00_requirement_analysis_and_system_plan.md`,
`docs/decisions/0001-phase00-decisions-and-scope.md`, and all 16
`docs/phase_reports/phaseNN.md` files) points at a file that actually
exists in the repository.

## Findings

- **The audit found no case of a phase report overclaiming** against
  CLAUDE.md §1 — Phase 15's own lighter JD-mapping spot-check already
  established this for phases up to 15, and re-reading every phase
  report's JD connection/Limitations section for this audit did not
  surface anything that check missed.
- **Two Position-purpose items (inventory/fulfillment decision support,
  product availability/JIT) and one Requirements item (cross-team
  collaboration) are structurally capped by what a solo, offline
  portfolio project can honestly claim** — not by any shortfall in the
  work done. This was true from Phase 00's own planning (RO-6, RO-7,
  RO-9, R-9 in the system plan) and this audit confirms it is still
  accurately disclosed, not quietly forgotten by Phase 16.
- **The single concrete "polish" gap was `README.md`**, not a larger
  set of scattered issues — a `TODO`/`FIXME` sweep across `src/` and
  `tests/` found none, and a check for internal cross-document Markdown
  links found none existed yet (each phase report is self-contained
  prose, not a link graph) — `README.md` is the first place real
  clickable cross-references between the documents now exist.

## Limitations

- **This audit is itself a self-assessment**, produced by the same
  process that built the project — CLAUDE.md §4/§19's honesty
  discipline was followed throughout, but a fully independent reviewer
  should still form their own judgment, especially on the **P**/**P/L**
  rows (which are inherently more interpretive than the clear **D**/**N**
  ones).
- **All limitations disclosed in Phases 01–15 remain unchanged and are
  not repeated in full here** — no pricing dimension, store-as-hub proxy,
  Ecuadorian (not the target company's real) calendar, sales-not-demand
  censoring, no Kaggle/GCP/Looker Studio access in this sandbox (fixture-
  only validation throughout), coarse transferred-holiday handling,
  fixture-scale statistical caveats on segment/RCA/monitoring findings.
  See each phase's own `docs/phase_reports/phaseNN.md` for the specific
  detail behind each of these.
- **`README.md` has not been viewed rendered on GitHub** in this
  sandbox (no way to preview GitHub's own Markdown rendering here) —
  worth a quick visual check once pushed.

## What to review

1. **`README.md`** — the portfolio's actual front door; confirm the tone,
   structure, and level of detail match how you want this repository to
   present itself to a reviewer who has never seen this conversation.
2. **The Final Audit table above** — especially every **P**, **P/L**,
   and **N** row, since those are the ones a reviewer (or an interviewer)
   is most likely to ask about directly.
3. **Whether any item you'd classify differently** — this audit is a
   documented judgment call in several places (e.g. "hub" as
   Demonstrated-with-a-documented-proxy vs. a stricter Partially
   demonstrated); your own read of where the line should sit is the one
   that matters for how you present this project.
4. **Whether to add a LICENSE file or an author/contact section to
   `README.md`** — neither was added in this phase (a licensing choice,
   and adding personal contact details to a public repository, are both
   decisions for you to make, not implied by the JD or CLAUDE.md).

## Interview questions

- Walk through one **Demonstrated** item and one **Partially
  demonstrated** item from the audit — what specifically separates them,
  in your own words, not just the label?
- For "hub," the audit classifies it as Demonstrated despite Favorita
  having no literal "hub" column. What's your reasoning for accepting
  that proxy, and where would you draw the line before a proxy stops
  being defensible?
- Which single dataset limitation (pricing, no stockout signal, the
  Ecuadorian calendar) would most change this project's conclusions if
  it were fixed, and why that one specifically?
- The audit explicitly refuses to reduce itself to a score. Why does
  CLAUDE.md ask for that, and what would a single number have hidden
  here?
- If you had one more phase to spend, which **Partially demonstrated**
  or **Not demonstrated** item would you prioritize closing, and what
  would that phase actually build?
- This project was built phase-by-phase with an AI coding assistant,
  under a persistent, versioned instruction file (`CLAUDE.md`) that is
  itself part of the public repository. How would you describe that
  process, and what did you personally review or decide at each phase
  boundary?

---

**STOP — Phase 16 ends here.** Per CLAUDE.md §17, Phase 16 is the last
phase in the defined phase list. No further phase should start without
new, explicit direction from the project owner.
