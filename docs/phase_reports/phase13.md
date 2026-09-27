# Phase 13 — BigQuery: Review Package

**Phase objective (from the Phase 13 prompt):** implement BigQuery only as
justified by the JD and project needs. Demonstrate analytical SQL/
warehouse capability and cost-conscious design. BigQuery is a plus in the
JD, not a mandatory requirement.

**Status: all 14 SQL models ported and offline-validated. Same real-access
gap as every other phase — no live GCP project or billing account exists
in this sandbox, so nothing here has ever executed against real BigQuery
— but "offline" did not mean "unverified": a real, dialect-aware parser
caught a real class of bug this phase's own testing narrative is built
around.**

---

## The justification (required before any code, per the phase objective)

BigQuery is a JD **bonus** signal (CLAUDE.md §3.5, §5), explicitly a plus,
not a requirement, and CLAUDE.md §9's cost principle says cloud tooling
should only be introduced when it adds meaningful evidence. This project
already has a complete, tested, 14-model layered SQL warehouse (staging →
intermediate → marts) running on DuckDB. Porting that exact warehouse to
BigQuery's SQL dialect is meaningful evidence for "analytical SQL/
warehouse capability" specifically because it is **not** a trivial
find-and-replace: DuckDB and BigQuery genuinely disagree on array
generation syntax, day-of-week numbering, date-truncation argument order,
and whether `DISTINCT` is allowed inside a window function — getting
these right (and demonstrating *how* they were verified, not just
asserted) is the real capability being shown. "Cost-conscious design" is
addressed directly through partitioning/clustering decisions made — and
explicitly *not* made — based on each table's actual scale.

---

## What was built

| Path | Purpose |
|---|---|
| `sql/bigquery/{staging,intermediate,marts}/*.sql` | All 14 models from the DuckDB warehouse, ported to BigQuery Standard SQL, same layering and filenames as `sql/{staging,intermediate,marts}/`. |
| `src/demandflow/bigquery/validate_sql.py` | `render_sql()` (the same `__TOKEN__`-substitution pattern `demandflow.transform.sql_runner` already uses, reused rather than reinvented), `validate_all()` / `check_sql_file()` — parses every file with `sqlglot` (`dialect="bigquery"`) and extracts structural facts (target table, partition column, cluster columns) for testing. |
| `scripts/bigquery_load_raw.sh` | The `bq load` commands that would populate the raw tables this SQL reads from, using the same Parquet files Phase 01's `convert` step already produces. Written and syntax-checked (`bash -n`); never executed, for the same reason nothing else here has run against live GCP. |
| `tests/unit/test_bigquery_sql.py` | 35 tests: every file parses, the partition/cluster design lands on exactly the right 3 of 14 tables, five specific dialect-correctness regressions are pinned, 7 files are cross-checked against `sqlglot`'s own automated DuckDB→BigQuery transpiler, and the load script's bash syntax is checked. |
| `pyproject.toml` | Added `sqlglot>=25.0` to the `dev` extra — pure-Python, no heavy/conflicting dependencies, safe to add directly (unlike Phase 12's Airflow, which needed full environment isolation). |

**Total test count: 313 passed + 1 skipped** (up from 279 + 1 — the
skipped test is still Phase 12's Airflow-only file; nothing about Phase 13
required environment isolation).

---

## Analytical SQL / warehouse capability: what actually had to be fixed

Six genuine DuckDB → BigQuery dialect differences were found and handled
— not by guessing, but by researching each function's real BigQuery
semantics and then locking the fix in as a test:

| # | DuckDB | BigQuery | Where |
|---|---|---|---|
| 1 | `UNNEST(generate_series(...))` works directly in a SELECT list | `UNNEST()` is a FROM-clause table operator; a **per-row** array (e.g. each item's own first/last sale date) needs a comma cross join to `UNNEST(GENERATE_DATE_ARRAY(...))` referencing the preceding FROM item | `int_sales_daily_dense.sql` |
| 2 | `EXTRACT(dow FROM date)` is 0=Sunday..6=Saturday | `EXTRACT(DAYOFWEEK FROM date)` is **1=Sunday..7=Saturday** — a silent, plausible-looking semantic bug if not normalized | `int_calendar_by_store.sql`, `dim_date.sql` |
| 3 | `date_trunc('month', date)` — `(part, date)` argument order | `DATE_TRUNC(date, MONTH)` — **reversed**, `(date, part)` | same two files |
| 4 | `EXTRACT(week FROM date)` already returns the ISO week number | `EXTRACT(WEEK FROM date)` is Sunday-based, non-ISO; `EXTRACT(ISOWEEK FROM date)` is the real equivalent | `dim_date.sql` |
| 5 | `COUNT(DISTINCT x) OVER (PARTITION BY ...)` — DISTINCT inside a window function | Not reliably supported; restructured to a `GROUP BY` + `JOIN` instead of trusting an uncertain feature | `stg_sales.sql` |
| 6 | `QUANTILE_CONT(x, p)` aggregate | `PERCENTILE_CONT(x, p) OVER ()` analytic function (exact/continuous, not `APPROX_QUANTILES`, to preserve the extreme-value fence's precision) | `stg_sales.sql` |

### The finding that validates the whole approach

To sanity-check the hand port, `sqlglot`'s own automated DuckDB→BigQuery
transpiler was run against the **original, untouched** DuckDB source
files. For the seven simple pass-through models, the auto-transpiled
output matched this phase's hand port exactly (same columns, same source
table) — a genuine structural cross-check, now a locked-in test.

For `int_calendar_by_store.sql` (items 2 and 3 above), the automated
transpiler produced **`EXTRACT(DOW FROM sd.date)`** — a DuckDB-only date
part with no BigQuery equivalent — and **`TIMESTAMP_TRUNC(sd.date, MONTH)`**
— a function that expects a `TIMESTAMP`, not the `DATE` column it was
applied to. Both are genuinely invalid BigQuery: they *parse* under
`sqlglot`'s more permissive grammar (confirmed directly — see
`test_sqlglots_naive_transpile_of_the_calendar_file_is_confirmed_wrong`),
but neither would compile against BigQuery's real query analyzer. This is
concrete, checked-not-assumed evidence that automated dialect translation
was not sufficient here, and that researching BigQuery's actual semantics
(not just its grammar) was the real work of this phase.

---

## Cost-conscious design

Only three of the fourteen tables get `PARTITION BY date CLUSTER BY
store_nbr, item_nbr`: **`stg_sales`**, **`int_sales_daily_dense`**, and
**`fct_sales_daily`** — the hub × SKU × day grain, at real scale, that
every forecasting/evaluation query in this project actually filters or
joins on. The eight dimension and small reference tables (`dim_hub`,
`dim_sku`, `dim_date`, `stg_stores`, `stg_items`, `stg_holidays_events`,
`stg_oil`, `stg_transactions`, `stg_dev_scope_items`) get neither —
explicitly, not by omission: at their scale (tens of stores, thousands of
items), partitioning or clustering would add metadata overhead for no
bytes-scanned benefit, which is exactly the "infrastructure for
appearance" CLAUDE.md §18 warns against.

### A worked example of why this matters for cost

BigQuery bills by bytes scanned. Consider a query this project's own
evaluation code issues constantly — one hub × SKU series' recent history:

```sql
SELECT * FROM fct_sales_daily
WHERE store_nbr = 1 AND item_nbr = 100 AND date >= '2013-01-01';
```

- **Without partitioning**, BigQuery must scan every column referenced
  across the *entire* table's storage — every date, every store, every
  item — to find the matching rows.
- **With `PARTITION BY date`**, BigQuery first prunes to only the
  partitions (individual days) on or after `2013-01-01`, never touching
  storage for earlier dates at all.
- **With `CLUSTER BY store_nbr, item_nbr`** on top, BigQuery further skips
  storage blocks *within* each remaining partition that don't contain
  `store_nbr = 1, item_nbr = 100`, since clustered storage is sorted by
  those columns.

At the real dataset's scale (~4.6 years, ~125M raw rows before the
development-scope filter), the difference between "scan the whole table"
and "scan the handful of partitions and blocks this query actually needs"
is the difference between a query that costs real money at scale and one
that costs a small fraction of it — for the exact same result. This
reasoning, not a rule of thumb, is why partitioning/clustering landed on
these three tables and nowhere else.

---

## Why this is still validated offline, not against live BigQuery

This sandbox has no real GCP project, no billing account, and no way to
authenticate interactively (BigQuery's free sandbox mode requires a
browser-based Google OAuth flow this environment cannot perform) — the
same category of real-access gap disclosed for Kaggle since Phase 01.
Docker is installed but its daemon is not running here, and this
session's GitHub access is scoped to this repository only, which rules
out a local BigQuery emulator (typically distributed as a Docker image or
a GitHub release binary) as well. What *is* real: every file was parsed
by an actual, independent, dialect-aware SQL parser — not read by eye —
and the specific bugs that parser's cross-check surfaced (`EXTRACT(DOW
...)`, `TIMESTAMP_TRUNC` on a `DATE`) are exactly the kind of error that
"looks right" without being run through anything.

### To complete the real run

```bash
# 1. Load the raw tables (requires a real GCP project + billing account)
PROJECT=my-gcp-project DATASET=demandflow \
DEMANDFLOW_DATA_DIR=/path/to/data \
    ./scripts/bigquery_load_raw.sh

# 2. Render and run each layer in order (staging, then intermediate, then marts)
python3 -c "
from demandflow.bigquery.validate_sql import list_sql_files, render_sql
from google.cloud import bigquery
client = bigquery.Client(project='my-gcp-project')
for f in list_sql_files():
    sql = render_sql(f.read_text(), 'my-gcp-project', 'demandflow')
    print(f'Running {f.name}...')
    client.query(sql).result()
"

# 3. Confirm the fact table actually partitioned/clustered as intended
bq show --format=prettyjson my-gcp-project:demandflow.fct_sales_daily
```

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"BigQuery is a plus" — demonstrated without claiming it as a hard requirement** | CLAUDE.md §3.5, §5 |
| **"Demonstrate analytical SQL/warehouse capability"** — a genuinely correct 14-model port, with 6 real dialect gotchas found, fixed, and tested, not a superficial re-typing | This phase's own objective line |
| **"Demonstrate ... cost-conscious design"** — partitioning/clustering justified by actual query patterns and table scale, with a worked bytes-scanned example, and explicitly *not* applied where it wouldn't help | This phase's own objective line; CLAUDE.md §9 |
| **"Strong SQL and experience working with large datasets; BigQuery is called out as a plus"** | CLAUDE.md §3.5 (requirements) |
| **Reproducible, documented, but never falsely claimed as executed** — the same honesty discipline as every prior phase's real-data-gap disclosure | CLAUDE.md §19 |

Not yet covered: Looker Studio / dashboard (Phase 14).

---

## Key decisions

- **`sqlglot` for offline validation, not a live dry-run.** BigQuery's own
  `dryRun` query option still requires live API access to a real project
  (credentials this sandbox doesn't have); `sqlglot` needed nothing but a
  pip install and gave genuine, dialect-aware syntax validation plus an
  automated-transpile cross-check — the strongest verification actually
  available here.
- **One dataset, not a raw/staging split across datasets.** Every table
  (`raw_*` through the final marts) lives in one BigQuery dataset,
  mirroring the DuckDB version's single-connection namespace exactly,
  rather than introducing a multi-dataset structure the original never
  had.
- **The `bq load` script loads Parquet files directly** (self-describing,
  no schema declaration needed) using the exact same files Phase 01's
  `convert` step already produces — no separate BigQuery-specific
  ingestion format was invented.
- **`sqlglot` was added directly to `pyproject.toml`'s dev extra**, unlike
  Phase 12's Airflow, which needed a fully isolated virtualenv. `sqlglot`
  is pure Python with no heavy or conflicting dependencies, so isolating
  it would have been unnecessary caution, not the same real risk Airflow's
  strict pins posed.
- **A real bug in the load script (not the SQL) was caught by `bash -n`**:
  an apostrophe inside a `${VAR:?message}` parameter expansion broke
  bash's parser even inside double quotes — fixed, and now a regression
  test, because this project's discipline treats a shell script the same
  as SQL or Python: validate it for real, don't just read it and assume.

## Validation

```
$ python3 -m pytest tests/ -q
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
.........................                                                [100%]
313 passed, 1 skipped in 113.96s

$ python -m demandflow.bigquery.validate_sql
[OK  ] sql/bigquery/staging/07_stg_sales.sql (partition=date, cluster=['store_nbr', 'item_nbr'])
[OK  ] sql/bigquery/intermediate/02_int_sales_daily_dense.sql (partition=date, cluster=['store_nbr', 'item_nbr'])
[OK  ] sql/bigquery/marts/04_fct_sales_daily.sql (partition=date, cluster=['store_nbr', 'item_nbr'])
... (11 more, all OK, none partitioned/clustered)
14/14 files parsed as valid BigQuery SQL
```

Both commands were actually run in this session; every finding above
(including the `EXTRACT(DOW ...)` / `TIMESTAMP_TRUNC` auto-transpile
result) is copied verbatim from real output, not reconstructed from memory.

## Findings

- **No findings about the real dataset** — this phase is about SQL
  portability and cost design, not new analysis.
- **Automated dialect transpilation is necessary but not sufficient** —
  confirmed directly, not assumed: `sqlglot`'s own transpiler produces
  invalid BigQuery for exactly the two constructs (day-of-week, date
  truncation) that needed real research into BigQuery's actual semantics.
- **Only 3 of 14 tables are large enough for partitioning/clustering to
  matter** — a genuine, scale-driven finding, not a rule applied uniformly.

## Limitations

- **Never executed against live BigQuery** — no real GCP project or
  billing account exists in this sandbox; no local emulator was reachable
  either (Docker's daemon isn't running here, and this session's GitHub
  access doesn't extend to downloading a third-party emulator binary).
  What's proven is syntactic validity and a structural cross-check against
  an independent transpiler, not runtime correctness against BigQuery's
  live query engine.
- **`sqlglot`'s BigQuery grammar is not a perfect substitute for
  BigQuery's own analyzer** — it accepted `EXTRACT(DOW ...)` as
  syntactically parseable even though real BigQuery has no such date
  part, which is exactly why this phase's tests check for the *absence*
  of known-wrong patterns as well as successful parsing, not parsing
  success alone.
- **`bq load`'s size limits for local (non-GCS) file uploads were not
  independently re-verified against current BigQuery documentation** —
  the load script documents the GCS-staging alternative for the real,
  full-scale `train.parquet` as the safer default for a real run.
- **All earlier phases' limitations still apply unchanged** (no Kaggle
  access, no pricing dimension, store-as-hub proxy, Ecuadorian calendar,
  coarse transferred-holiday handling).

## What to review

1. **The six dialect-difference fixes** — confirm each one (day-of-week
   normalization, `DATE_TRUNC` argument order, `ISOWEEK`, the
   `COUNT(DISTINCT...) OVER()` restructuring, `PERCENTILE_CONT`) against
   BigQuery's own documentation if you want a second, independent check
   beyond this session's research.
2. **The partition/cluster scope decision** — confirm you're comfortable
   that only the 3 large tables get it, and that the worked cost example
   is a fair characterization of the tradeoff.
3. **The `sqlglot`-vs-real-BigQuery gap** — confirm the Limitations
   section's framing (offline syntax validation is real evidence, not a
   substitute for a live run) matches how you'd want this represented to
   an interviewer.
4. **Run the real load + query sequence** once real GCP access exists —
   the commands are in "To complete the real run" above.

## Interview questions

- Walk through the day-of-week numbering difference between DuckDB and
  BigQuery, why it's a silent bug risk, and how this port's tests catch a
  regression of it.
- Why does `stg_sales.sql` compute duplicate/conflict counts with a
  `GROUP BY` + `JOIN` instead of `COUNT(DISTINCT x) OVER (...)`, and what
  would you need to verify before trusting the window-function form
  instead?
- What did running `sqlglot`'s automated transpiler against the original
  DuckDB SQL actually prove, and why was that more valuable than just
  hand-translating and moving on?
- Why do only 3 of the 14 tables get `PARTITION BY` / `CLUSTER BY`, and
  what would you look at on the real dataset to confirm that scope is
  still right at full scale?
- What's the practical difference between "this SQL parses under a
  dialect-aware parser" and "this SQL would actually run correctly on
  live BigQuery," and where does this phase draw that line explicitly?
- If real GCP access became available tomorrow, what's the very first
  thing you'd check before trusting this port's output?

---

**STOP — Phase 13 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 14 (Looker Studio / Dashboard) has not
started.
