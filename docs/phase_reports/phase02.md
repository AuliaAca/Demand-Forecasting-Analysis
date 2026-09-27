# Phase 02 — Data Quality: Review Package

**Phase objective (from the Phase 02 prompt):** implement data-quality profiling
relevant to the sales/demand workflow. Detect missing dates, duplicates,
null/invalid keys, suspicious values, date gaps, grain problems, and missing
JD-relevant dimensions. Document severity and downstream behavior.

**Status: code complete and tested against a synthetic fixture. Same
real-data gap as Phase 01 — see below.**

---

## What was built

| Path | Purpose |
|---|---|
| `src/demandflow/quality/rules.py` | The DQ rule catalog: 8 rules, each returning a `DQFinding` (rule, category, description, metrics, severity, consequence, handling decision) — CLAUDE.md §12's exact documentation contract. |
| `src/demandflow/reporting/generate_dq_report.py` | Renders `docs/data_quality/dq_report.md` from `reports/phase02/dq_findings.json` — generated, never hand-typed, same principle as Phase 01's dataset-card generator. |
| `tests/unit/test_dq_rules.py`, `test_generate_dq_report.py` | 13 new tests, all passing. |
| `tests/fixtures/favorita_sample/train.csv` | Extended with one more planted issue: an extreme value (`unit_sales=80.0`, everything else in the fixture is 1–7) — needed to exercise the new outlier-screening rule. Total fixture rows: 51 → 52. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended to run the DQ rules and render the DQ report as steps 7–8 of the same end-to-end smoke test. |

**Total test count: 37 (24 from Phase 01 + 13 new), all passing.**

### The 8 rules

| Rule ID | Category | What it checks | On the fixture |
|---|---|---|---|
| `grain_duplicates` | grain | `(date, store_nbr, item_nbr)` repeated; escalates to CRITICAL if repeats disagree on `unit_sales`/`onpromotion` | 1 duplicate group, not conflicting → **HIGH** |
| `null_keys` | keys | NULL date/store_nbr/item_nbr | none → **PASS** |
| `orphan_dimension_keys` | dimensions | sales rows referencing a store/item absent from the dimension tables | 1 orphan item → **HIGH** |
| `missing_calendar_dates` | dates | calendar dates with zero rows network-wide | 1 of 20 days (5%) → **MEDIUM** |
| `suspicious_negative_values` | values | negative `unit_sales` (returns, per public documentation) | 1 row → **LOW** (expected pattern) |
| `suspicious_extreme_values` | values | positive `unit_sales` beyond a Q3+3×IQR fence — a coarse DQ-level screen, not Phase 04/09's context-aware anomaly analysis | 1 row (80.0) → **MEDIUM** |
| `onpromotion_missing` | values | NULL `onpromotion` | 5 of 52 rows (9.6%), below the 20% high-severity threshold → **MEDIUM** |
| `missing_pricing_dimension` | dimensions | whether any acquired table carries item-level pricing at all — a dataset-level structural check, not a row scan | no pricing table → **INFO** |

Every rule's severity is justified inline by what the issue actually does downstream (see the code's comments and the rendered report), not read off one generic percentage table — different issue types carry different risk at the same prevalence.

**Not built in this phase, on purpose:** no remediation code. Every
`handling_decision` above names what Phase 03's staging layer will do
(deduplicate, quarantine, flag-and-keep) — Phase 02 documents the decision;
Phase 03 implements it. CLAUDE.md §12's "do not silently remove problematic
records" rule is satisfied by construction: every handling decision either
keeps the row with a flag or names an explicit, inspectable quarantine
location (never a silent drop).

---

## Why this is still validated on the fixture, not real data

Same situation as Phase 01, carried forward unchanged: this sandbox has no
Kaggle network access or credentials, and ADR 0001 already assigns the real
run to your own machine (`D:\`). Nothing changed on that front since Phase
01 — I have no report back yet from a local run.

**This matters more in Phase 02 than it did in Phase 01.** Phase 01's
checks are purely descriptive (row counts, schema) — a fixture proves the
*mechanism* works. Phase 02 additionally assigns **severity**, and several
severity thresholds here are calibrated against *expected real-world shares*
(e.g., `onpromotion_missing` escalates to HIGH above 20% NULL, chosen because
public write-ups report ~16% NULL on the real file — close enough to the
threshold that the real number matters). On the tiny fixture, these
thresholds are exercised for correctness (does the branching logic work at
all) but not meaningfully validated at realistic prevalence. **The severities
in this phase's fixture-based report should not be read as predictions of
what the real dataset's DQ report will say** — only the rule logic and the
documentation contract are proven; the real findings are still pending.

The extreme-value rule (`suspicious_extreme_values`) is newer territory
still: its IQR fence is fit fresh from whatever data it's given, so it will
behave very differently at ~12M+ rows than on 52. That's expected and fine
— the point of this phase was to build and prove the *mechanism*, not to
report Favorita's real DQ profile yet.

### To complete the real run

Same commands as Phase 01, now including the DQ steps:

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 37/37 pass on this machine too
make phase01            # acquire, convert, profile, select-scope, dataset-card
make phase02            # dq, dq-report
```

Whatever comes back — including if a severity threshold turns out to be
miscalibrated against the real data's actual distribution — is the real
Phase 02 result to act on, not something this session can pre-decide.

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Investigating data issues** with a documented rule/finding/severity/consequence/handling-decision format | Missions: "Investigate data issues... perform root-cause analysis" (this phase detects and documents; Phase 09 does the deeper RCA) |
| **Suspicious demand values** and **outliers** — a first, coarse detection pass | Missions: "identifying trends, seasonality, **outliers**, and demand anomalies" (Phase 02's screen is deliberately coarse; Phase 04/09 do the context-aware analysis) |
| **Missing JD-relevant dimensions**, made explicit and structural (not silently absent) | CLAUDE.md §3.1: "If a dimension is unavailable: document the limitation... do not claim the requirement was fully demonstrated" |
| **Strong SQL** and **attention to detail** — every rule is a DuckDB SQL query with an explicit, justified severity rationale | Requirements: "Strong SQL"; "great attention to detail" |
| Beginning of **cross-functional routing**: the orphan-dimension-key finding is explicitly routed to a Data Engineering stakeholder perspective | Missions: "work with relevant teams to resolve them" (simulated perspective, per ADR 0001 — not real collaboration) |

This phase does not yet provide evidence for forecasting, monitoring,
dashboards, alerts, BigQuery, or the deeper RCA workflow (Phase 09) — those
are later phases.

---

## Key decisions

- **Severity is per-rule, not a single generic threshold table.** Each
  rule's severity logic is justified by what the issue actually breaks
  downstream (documented inline in `rules.py` and visible in the rendered
  report's "Consequence" field).
- **`onpromotion_missing` escalates past 20% NULL** — a `[DECISION]`
  threshold (`ONPROMOTION_NULL_HIGH_SEVERITY_THRESHOLD`), not a JD figure,
  chosen because that's meaningfully worse for the JD's "campaigns"
  dimension than the ~16% publicly reported on the real file.
- **The extreme-value screen is deliberately coarse** (a global Q3+3×IQR
  fence on positive values) and explicitly labeled as a DQ-level screen,
  not the demand-anomaly analysis Phase 04/09 will do — kept simple so it
  doesn't quietly duplicate later, more careful work.
- **`grain_duplicates` distinguishes agreeing vs. conflicting duplicates**
  and only escalates to CRITICAL when they conflict — an exact repeat is a
  narrower problem (drop the extra row) than two different values claiming
  the same key (which one is right?).
- **The fixture was extended, not replaced**, to cover the new
  extreme-value rule — documented here rather than silently changing
  Phase 01's already-committed numbers. Phase 01's own review package
  (`docs/phase_reports/phase01.md`) still describes the fixture as it stood
  at that phase (51 rows) and is left as the historical record, not
  rewritten.

## Validation

```
$ make test
....................................  [100%]
37 passed in 1.61s

$ make smoke   # extended to include DQ steps 7-8; run, inspected, then cleaned up
...
[7/8] Running the Phase 02 data-quality rule catalog
       grain_duplicates=HIGH, null_keys=PASS, orphan_dimension_keys=HIGH,
       missing_calendar_dates=MEDIUM, suspicious_negative_values=LOW,
       suspicious_extreme_values=MEDIUM, onpromotion_missing=MEDIUM,
       missing_pricing_dimension=INFO
[8/8] Rendering the DQ report (fixture preview — NOT the real DQ report)
Smoke test complete.
```

Both commands were actually run in this session; `make clean-smoke` removed
the output afterward (git-ignored anyway, so it was never at risk of being
committed).

## Findings

- **No findings yet about the real dataset** — none to honestly report
  until a real profiling run exists.
- **On the fixture:** every planted issue was caught with the expected
  severity, including the new conflicting-vs-agreeing duplicate distinction
  (verified with an extra, test-only synthetic conflict row that is not
  part of the committed fixture — see `test_grain_duplicates_conflicting_escalates_to_critical`).
- **A design point worth flagging for your review:** `orphan_dimension_keys`
  currently treats an unknown item and an unknown store as similar severity
  (both HIGH once present) because either one blocks category/hub-segmented
  analysis for that row. If you'd rather they be scored differently, that's
  an easy, isolated change.

## Limitations

- **Real Kaggle files still unverified** (see above) — carried over from
  Phase 01, now also affecting whether the severity *thresholds* are well
  calibrated, not just whether the *detection logic* runs.
- **`docs/data_quality/dq_report.md` does not yet exist**, for the same
  honesty reason `docs/dataset_card.md` doesn't yet exist: generating it now
  from fixture data and presenting it as Favorita's real DQ report would
  violate CLAUDE.md §19. Run `make phase02` after a real profiling run to
  produce it.
- **The extreme-value fence is unvalidated at scale.** A global IQR fence
  computed over ~12M+ real rows (rather than 52) may need per-family or
  per-item scoping instead of one global fence — this is exactly the kind
  of thing only the real data can tell us, and is worth revisiting once it
  exists.
- **All Phase 00/01 limitations still apply unchanged** (no pricing, no
  stockout signal, store-as-hub proxy, Ecuadorian calendar).

## What to review

1. **`src/demandflow/quality/rules.py`** — read each rule's severity
   rationale (inline comments); tell me if any reasoning doesn't hold up.
2. **The extreme-value fence design** (`EXTREME_VALUE_IQR_MULTIPLIER = 3.0`,
   computed globally on positive values) — flag now if you'd rather it be
   scoped per item/family from the start, before Phase 03 builds on top of
   whatever flag column this produces.
3. **The `onpromotion_missing` 20% threshold** — reasonable, or would you
   set it differently?
4. **Run `make phase01 && make phase02` locally** once Kaggle access
   exists, and send back what comes out — especially whether any rule's
   severity looks wrong at real scale.

## Interview questions

- Why does `grain_duplicates` only escalate to CRITICAL when duplicate rows
  *disagree* on a value, rather than treating every duplicate as equally
  severe?
- Why is the extreme-value check described as "coarse" and explicitly
  distinguished from Phase 04/09's anomaly analysis — what would a
  more context-aware version need that this one doesn't have?
- Why does `missing_pricing_dimension` get severity INFO rather than HIGH or
  CRITICAL, given pricing is one of the JD's six named analysis dimensions?
- What's the actual mechanism (in code and in the generated report) that
  prevents a data-quality issue from ever being silently dropped, per
  CLAUDE.md §12?
- Why is severity assigned per-rule with its own justification, instead of
  one shared percentage-based table applied to every rule?
- The `onpromotion_missing` threshold was set using a public [VERIFY] figure
  from Phase 00 research, not the real profiled data. What's the risk in
  that, and how would you know if it needs to change?

---

**STOP — Phase 02 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 03 (SQL & Data Modeling) has not started.
