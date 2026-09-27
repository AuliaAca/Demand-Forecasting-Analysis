# Phase 03 — SQL & Data Modeling: Review Package

**Phase objective (from the Phase 03 prompt):** implement analytical SQL/data
modeling that demonstrates the JD's SQL requirement. Define grain, keys,
transformations, reusable analytical datasets, and validation. Use BigQuery
only if this phase's design requires it; otherwise keep the workflow local.

**Status: code complete and tested against the synthetic fixture. Same
real-data gap as Phases 01–02 — see below.** BigQuery was **not** used —
nothing in this phase's design requires it; DuckDB is sufficient locally
(ADR 0001 D5/D7 already reserve BigQuery for Phase 13).

---

## What was built

A layered SQL warehouse — **raw → staging → intermediate → marts** — built
from plain `.sql` files plus a small Python runner (no dbt, per ADR 0001 D6),
and this is where Phase 02's data-quality *decisions* finally become
*mechanism*.

| Path | Purpose |
|---|---|
| `sql/staging/01–08_*.sql` | One `CREATE OR REPLACE TABLE` per file, run in filename order. `07_stg_sales.sql` is the important one — see below. |
| `sql/intermediate/01_int_calendar_by_store.sql` | A store × day calendar with national/regional/local holidays resolved per store's city/state, plus an approximate payday flag. |
| `sql/intermediate/02_int_sales_daily_dense.sql` | The dense hub × SKU × day grid, filled only within each item-hub pair's *active window* (Phase 00 assumption A3), never outside it. |
| `sql/marts/01–04_*.sql` | `dim_hub`, `dim_sku`, `dim_date`, `fct_sales_daily` — reusable, documented analytical tables. |
| `src/demandflow/transform/sql_runner.py` | Registers raw Parquet files as DuckDB views; runs a `.sql` layer directory in filename order; does simple `__TOKEN__` path substitution (not a templating engine) for the one file that needs a filesystem path. |
| `src/demandflow/transform/validate.py` | 7 reconciliation checks — grain uniqueness, row-count reconciliation, dimension completeness, no-null-keys, DQ round-trip, and the orphan-item non-drop guarantee. |
| `src/demandflow/transform/build_warehouse.py` | Orchestrates the above end-to-end and loads Phase 02's DQ findings into a new mart, `fct_dq_result`. |
| `tests/unit/test_build_warehouse.py`, `test_sql_constants_sync.py` | 13 new tests, all passing. |
| `scripts/run_fixture_smoke_test.py`, `Makefile` | Extended with a 9th step: build the warehouse and print reconciliation results. New targets: `make warehouse`, `make phase03`. |

**Total test count: 50 (37 from Phases 01–02 + 13 new), all passing.**

### Where Phase 02's handling decisions actually get implemented

| Phase 02 rule | Handling decision | Where it's implemented now |
|---|---|---|
| `grain_duplicates` | Keep one row per key; highest `id` wins on conflict | `07_stg_sales.sql`'s `ROW_NUMBER() ... ORDER BY id DESC` |
| `null_keys` | Quarantine, never load into the fact table | `08_stg_sales_rejected_null_keys.sql` (a named, inspectable table) |
| `orphan_dimension_keys` | Keep the row, flag it, never drop it | `has_unknown_item` / `has_unknown_store` columns in `stg_sales` |
| `suspicious_negative_values` | Keep, flag as `is_return` | `stg_sales.is_return` |
| `suspicious_extreme_values` | Keep, flag as `is_extreme_value` | `stg_sales.is_extreme_value`, fence fit on the full raw table |
| `onpromotion_missing` | Keep NULL as a distinct state | `stg_sales.is_promotion_unknown` (never coerced) |
| `missing_pricing_dimension` | Document only, no row-level fix applies | Unchanged — still just documented |

### A design issue caught and fixed while building this

The controlled development scope (ADR 0001 §2) restricts the sales fact
table to a stratified sample of *known* items. Item `999` in the fixture
doesn't exist in `items.csv` at all — it's Phase 02's planted orphan-item
row. A naive `WHERE item_nbr IN (SELECT item_nbr FROM dev_scope_items WHERE
selected)` filter would have **silently dropped it**, because an unrecognized
item can never appear in a selection built from the known item catalog. That
would have quietly undone Phase 02's explicit "keep and flag, never drop"
decision. `07_stg_sales.sql` fixes this: the scope filter is `item_nbr IN
(selected) OR item_nbr NOT IN (known items)` — an orphan item is let through
regardless of scope, because it isn't a recognized SKU that scope filtering
even applies to. `test_orphan_item_row_kept_and_flagged_despite_dev_scope_filter`
and reconciliation check #7 both lock this in.

---

## Why this is still validated on the fixture, not real data

Unchanged from Phases 01–02: no Kaggle network access or credentials in this
sandbox; the real run is your machine's job per ADR 0001. Every SQL file was
run for real against the fixture in this session (not just written) — all 7
reconciliation checks pass, and every hand-countable fact (the store-1/item-100
dense grid: 20 days, 13 real, 7 imputed, at exactly the predicted dates; the
holiday resolution: national holidays hit all 5 stores, the Quito-local
holiday hits only stores 1–2, the transferred bridge holiday passes through
correctly) matches by hand-count, not just by the code "running without
error." What's still unverified is real Kaggle data flowing through this —
in particular, whether the `.7z` extraction (Phase 01) and the assumed schema
survive contact with the actual files, and whether the extreme-value fence
and dev-scope sampling behave sensibly at ~12M+ rows instead of 52.

### To complete the real run

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q     # confirm 50/50 pass on this machine too
make phase01
make phase02
make phase03            # builds the warehouse, prints reconciliation results
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **Strong SQL**, applied at the core of the pipeline: window functions (`ROW_NUMBER`, partitioned counts), multi-condition joins, `generate_series`/`UNNEST` for dense grids, `QUANTILE_CONT`, date functions | Requirements: "Strong SQL and experience working with large datasets" |
| **Reusable analytical datasets** with a documented, enforced grain | Missions: "Build automated **datasets**"; CLAUDE.md engineering principles: "clear data contracts/grain" |
| **Hubs, categories, seasonal events** made queryable as proper dimensions (`dim_hub`, `dim_sku` with family/class/perishable, `int_calendar_by_store` with resolved holidays) | Missions: "Analyze demand patterns across... hubs, categories... seasonal events" |
| **Data issues actually handled**, not just documented — the exact mechanism CLAUDE.md §12's "do not silently remove problematic records" describes | Missions: "Investigate data issues... work with relevant teams to resolve them" |
| **Validation / reconciliation** as a first-class step, not an afterthought | CLAUDE.md engineering principles: "validation... reproducibility" |
| Early **scalable-solutions** evidence: the same SQL files are what would run, unmodified, against a larger dev-scope fraction or the full dataset (only the dev-scope CSV's contents would change) | Missions: "build scalable solutions" |

This phase does not yet provide evidence for forecasting, evaluation,
monitoring, dashboards, alerts, or BigQuery (Phase 13) — those are later
phases. Pricing (M-1e) remains undemonstrated — no pricing data exists in
this dataset (ADR 0001 D2), unchanged.

---

## Key decisions

- **The development scope filter must never override Phase 02's "don't
  silently drop" rule.** An orphan item is let through regardless of scope
  — see "A design issue caught and fixed" above. This is the phase's most
  important modeling decision.
- **The extreme-value fence is fit on the full raw table, not the dev-scope
  sample** — a ~10% item sample would make the fence noisier and would
  drift every time the sample is redrawn. The `3.0` multiplier in
  `07_stg_sales.sql` must match `quality.rules.EXTREME_VALUE_IQR_MULTIPLIER`;
  a dedicated pin test (`test_sql_constants_sync.py`) catches drift, since
  SQL text can't import a Python constant.
- **Dimension tables stay complete; only the fact table is scoped.**
  `dim_hub` and `dim_sku` always cover every store and every item in the
  raw catalog (enforced by reconciliation checks 3–4) — the development
  scope is a fact-table row-volume control, not a reason to make a
  dimension table incomplete.
- **`fct_sales_daily` is a materialized copy of `int_sales_daily_dense`,
  not a trimmed one.** Intermediate vs. mart here is a pipeline-
  organization distinction (working table vs. documented serving table),
  not a column-reduction step — the DQ flags are genuinely useful to
  Phase 04+, not just internal debugging noise.
- **Holiday "transferred" semantics are deliberately not fully resolved.**
  The real Favorita data marks some holidays as observed on a different day
  than their calendar date; `int_calendar_by_store` passes the `transferred`
  flag through but does not re-map the true observed date. Flagged here as
  a limitation rather than silently assumed correct.
- **`fct_dq_result` is loaded from Python, not a `.sql` file.** Its source
  is the `DQFinding` dataclasses Phase 02 already authored in Python
  (severity/consequence text is naturally written there, not derived by a
  SQL aggregation); loading it into a table afterward for queryability is a
  normal pattern, not a gap in the SQL layer.

## Validation

```
$ make test
..................................................  [100%]
50 passed in 4.60s

$ make smoke   # 9 steps, ending with the warehouse build + reconciliation
...
[9/9] Building the SQL warehouse (staging -> intermediate -> marts) and reconciling
[PASS] fct_sales_daily_grain_unique: 154 rows, 154 distinct (store_nbr,item_nbr,date) keys
[PASS] real_rows_reconcile_with_staging: stg_sales=51, fct_sales_daily non-imputed=51
[PASS] dim_hub_covers_all_stores: raw_stores=5, dim_hub=5
[PASS] dim_sku_covers_full_catalog: raw_items=10, dim_sku=10
[PASS] no_null_keys_in_fact_table: 0 null-key rows
[PASS] fct_dq_result_has_all_rules: 8 rows (expected 8)
[PASS] orphan_item_rows_not_silently_dropped: stg_sales has_unknown_item=1, fct_sales_daily=1
Smoke test complete.
```

Both commands were actually run in this session; output above is copied
from the real run, then cleaned up (`make clean-smoke`; git-ignored anyway).

## Findings

- **No findings yet about the real dataset.**
- **On the fixture, every transformation was spot-checked by hand, not just
  asserted to "run without error":** the store-1/item-100 active window
  (20 days, 13 real, 7 imputed at exactly the 7 predicted dates), the
  national/local/transferred holiday resolution, the duplicate-key dedup
  (highest `id` wins, correctly identified as non-conflicting), and the
  orphan-item survival through the scope filter.
- **A real design flaw was found and fixed during this phase** (the
  dev-scope filter silently dropping orphan items) — worth surfacing
  explicitly since it's exactly the kind of interaction between two
  independently-reasonable decisions (scope filtering; DQ flagging) that's
  easy to miss until you build the thing.

## Limitations

- **Real Kaggle files still unverified** — carried over unchanged.
- **Transferred-holiday resolution is incomplete** (see Key decisions).
  Revisit if Phase 04's seasonality analysis needs the true observed date
  rather than the origin date.
- **The extreme-value fence is unvalidated at real scale** — same caveat as
  Phase 02, now also affecting a materialized column instead of just a
  report.
- **`int_calendar_by_store` is store × day, not hub-network-day** — it
  doesn't yet aggregate to a network-wide calendar view; that's naturally a
  Phase 04 EDA concern, not a Phase 03 modeling one.
- **All Phase 00–02 limitations still apply unchanged** (no pricing, no
  stockout signal, store-as-hub proxy, Ecuadorian calendar).

## What to review

1. **`sql/staging/07_stg_sales.sql`** — the file where every Phase 02
   decision becomes real; read its header comment against Phase 02's rule
   catalog and confirm each mapping is right.
2. **The dev-scope-filter fix** (orphan items let through regardless of
   scope) — confirm this is the behavior you want; the alternative (only
   ever loading recognized, in-scope items) is a one-line change if you'd
   rather orphan items go to a separate rejects table instead of staying in
   the main fact table.
3. **`sql/intermediate/01_int_calendar_by_store.sql`**'s holiday-locale
   join logic — worth a careful read since it's the most complex query in
   the phase.
4. **Run `make phase01 && make phase02 && make phase03` locally** once
   Kaggle access exists, and check the reconciliation checks still all pass
   at real scale — particularly `fct_dq_result_has_all_rules` (still
   expects exactly 8) and the row-count reconciliation.

## Interview questions

- Walk through why `07_stg_sales.sql`'s scope filter is `item_nbr IN
  (selected) OR item_nbr NOT IN (known items)` rather than just `item_nbr IN
  (selected)` — what would the simpler version have silently done wrong?
- Why is the extreme-value fence computed from `raw_train` (the full table)
  inside a staging model that otherwise only processes the dev-scope subset?
- Why are `dim_hub` and `dim_sku` never restricted by the development scope,
  while `fct_sales_daily` is?
- What's the difference between `int_sales_daily_dense` and
  `fct_sales_daily`, and why do both exist instead of just one?
- Why does deduplication keep the highest `id` on a conflicting duplicate
  instead of, say, the maximum `unit_sales` value?
- What would you need to change to point this same SQL at a larger
  development-scope fraction, or the full dataset, in BigQuery instead of
  DuckDB (Phase 13)? What, if anything, would need to change in the SQL
  files themselves?

---

**STOP — Phase 03 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 04 (Exploratory Demand Analysis) has not
started.
