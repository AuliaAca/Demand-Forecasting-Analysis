# Phase 01 — Dataset: Review Package

**Phase objective (from the Phase 01 prompt):** evaluate and select a public dataset
against the target-role JD dimensions in `CLAUDE.md`, acquire/prepare it, inspect
schema/grain/size/time coverage, document which JD dimensions are supported or
missing, and validate downstream suitability.

**Status: code complete and tested against a synthetic fixture. Not yet run
against the real Kaggle data.** See §"Why the real run hasn't happened yet"
below before treating this phase as finished.

---

## What was built

A runnable, tested Python pipeline under `src/demandflow/`, plus its tests and
a Makefile to drive it:

| Path | Purpose |
|---|---|
| `pyproject.toml` | Package metadata; dependencies: `duckdb`, `pandas`, `pyyaml`, `kaggle`, `py7zr`; dev dependency `pytest`. |
| `configs/project.yaml` | Kaggle competition slug, data-dir env var name, and the dev-scope sampling parameters (target fraction, quantiles, promo threshold) — all `[DECISION]`, not JD facts. |
| `src/demandflow/config.py` | Loads `project.yaml`; resolves the data root from `DEMANDFLOW_DATA_DIR` so the same code runs in this sandbox and on the project owner's `D:\` (ADR 0001 §4.3). |
| `src/demandflow/ingest/acquire_favorita.py` | Kaggle API download, `.7z`/`.zip` extraction, SHA-256 checksums, `manifest.json`. |
| `src/demandflow/ingest/convert_to_parquet.py` | CSV → Parquet via DuckDB, explicit asserted schema, out-of-core (no pandas.read_csv on the full file). |
| `src/demandflow/profiling/checks.py` | Reusable, individually-tested inspection functions: schema, grain uniqueness, null keys, date-gap detection, value validity, referential integrity, dimension coverage. |
| `src/demandflow/profiling/profile_favorita.py` | Orchestrates the checks above into one `profile_summary.json`. |
| `src/demandflow/scope/select_dev_scope.py` | The stratified, seeded, reproducible development-scope sampler from ADR 0001 §2 (family × perishable × volume-tier × promo-intensity). |
| `src/demandflow/reporting/generate_dataset_card.py` | Renders `docs/dataset_card.md` from the profiling + dev-scope JSON — never hand-typed. |
| `tests/fixtures/favorita_sample/` | A small, hand-built, **deliberately dirty** synthetic dataset matching Favorita's public schema (51 sales rows, 5 stores, 10 items, 3 holiday entries) — see below. |
| `tests/unit/*.py` | 24 tests, all passing, exercising every module above against the fixture. |
| `scripts/run_fixture_smoke_test.py` | Runs the *entire* pipeline (acquire → convert → profile → select scope → dataset card) end-to-end against the fixture in one command, writing to a git-ignored, clearly-labeled `reports/phase01/fixture_smoke_test/` directory that can never be mistaken for a real dataset card. |
| `Makefile` | `make install`, `make test`, `make smoke`, and the real pipeline targets `acquire` / `convert` / `profile` / `select-scope` / `dataset-card` / `phase01`. |

**Not built in this phase, on purpose (phase discipline, CLAUDE.md §18):** no
staging/intermediate/mart SQL (Phase 03), no data-quality rule/severity/
handling-decision catalog (Phase 02 — this phase only *describes* what's in
the data, it doesn't classify or remediate it), no forecasting code.

---

## Why the real run hasn't happened yet

This session runs in an isolated cloud container, separate from the project
owner's own machine. Two things block a real run **here**:

1. **Network policy.** `kaggle.com` is blocked at this container's egress
   proxy (`CONNECT tunnel failed, response 403`, confirmed by direct test).
2. **No credentials.** No `KAGGLE_USERNAME`/`KAGGLE_KEY` are configured in
   this sandbox.

Separately, ADR 0001 (§4.3) already decided this project runs on the project
owner's own Windows machine, from `D:\`, not in a disposable cloud container
— so even if this container's network were opened up, downloading ~5 GB into
a throwaway sandbox would not be the right outcome anyway.

**What was actually validated instead:** every module was exercised against
a small, hand-built, deliberately dirty fixture (`tests/fixtures/favorita_sample/`)
that mirrors Favorita's real, public schema. The fixture plants one duplicate
`(date, store_nbr, item_nbr)` row, one negative `unit_sales`, one fractional
`unit_sales`, five `NULL onpromotion` values, one row referencing an
`item_nbr` absent from `items.csv`, and one entirely missing calendar date —
and every check correctly finds every one of them (24/24 tests pass). This
proves the pipeline's logic is sound. It does **not** prove the real Kaggle
files parse identically — real files can have encoding quirks, an
`.7z`/`.zip` layout different from what's assumed, or a schema drift the
public documentation didn't mention. That first real run is genuinely
unverified, and this document says so rather than presenting invented
numbers as if they came from real data (CLAUDE.md §19).

### To complete the real run

On the project owner's Windows machine, with `D:` set per ADR 0001 §4.3:

```powershell
$env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
$env:KAGGLE_USERNAME = "..."
$env:KAGGLE_KEY = "..."
pip install -e ".[dev]"
python -m pytest -q          # confirm 24/24 pass on this machine too
make phase01                 # or run the 5 steps in the Makefile by hand
```

This accepts the Kaggle competition's rules on kaggle.com first (the API
refuses the download otherwise). Whatever comes back — a clean run, or a
schema mismatch this code doesn't yet handle — is the real Phase 01 result;
this session cannot fabricate it.

---

## JD connection

Per the target-role profile in `CLAUDE.md` §1 (anonymized; see ADR 0001 §3
for why no company name appears anywhere in this repository):

| What this phase provides evidence for | JD reference |
|---|---|
| Working with **large datasets**, and using **SQL** (DuckDB) to transform data | Requirements: "Strong SQL and experience working with large datasets" |
| Comfortable using **Python** for analysis and automation | Requirements: "Comfortable using Python for analysis and automation" |
| Investigating **data issues** (grain duplicates, orphan keys, missing dates, invalid values) | Missions: "Investigate data issues... perform root-cause analysis" (root-cause analysis itself is Phase 09 — this phase only detects and describes) |
| Determining which **SKU / hub / category / campaign / pricing / seasonal-event** dimensions the chosen dataset actually supports | Missions: "Analyze demand patterns across SKUs, hubs, categories, campaigns, pricing, and seasonal events" — Phase 00's CLAUDE.md §3.1 rule: document what's unavailable rather than claim it |
| A **reproducible** dataset artifact (checksummed, versioned selection query, seeded sampling) | Engineering principles (CLAUDE.md §14): reproducibility, validation |
| Beginning of **scalable solutions**: the full-file profiling step runs on the complete dataset via DuckDB without needing it to fit in RAM, while everything downstream uses a documented, resizable scope | Missions: "build scalable solutions" |

This phase does **not** yet provide evidence for forecasting, monitoring,
dashboards, alerts, BigQuery, or RCA — those are later phases.

---

## Key decisions

All carried over from Phase 00 (`docs/decisions/0001-phase00-decisions-and-scope.md`),
implemented here rather than re-decided:

- **DuckDB over pandas for the full-file step** — disk-spillable, not
  RAM-bound (ADR 0001 §4.1). Confirmed in code: `convert_to_parquet.py` never
  calls `pandas.read_csv()` on the raw files.
- **Explicit, asserted schema** on CSV→Parquet conversion (not type
  inference) — a real schema surprise fails loudly (`ValueError` naming the
  missing columns) instead of silently coercing data.
- **Stratified, seeded item sampling** — every stratum cell gets its own
  `random.Random` seeded from the global seed plus the cell's own key, so
  resizing one cell never perturbs another's draw (see
  `select_dev_scope.stratify_and_sample`).
- **The dataset card is generated, never hand-typed** — it reads
  `profile_summary.json` (and the dev-scope summary) and renders Markdown
  from it, so every number in it traces back to one profiling run.
- **New in this phase:** the frozen dev-scope item list writes to
  `configs/dev_scope_items.csv` (a small, committable list of item IDs — not
  raw data), while the fuller per-item stats and JSON summaries are run
  outputs under `reports/`, not committed (ADR 0001 §2.4's reproducibility
  requirement, without treating a report as source).

## Validation

```
$ make test
python -m pytest -q
........................                                               [100%]
24 passed in 0.87s

$ make smoke        # full pipeline, fixture data, then `make clean-smoke`
[1/6] ... [2/6] 'Acquiring' ... [3/6] Converting ... {'train': 51, 'stores': 5,
'items': 10, 'holidays_events': 3, 'oil': 10, 'transactions': 16}
[4/6] Profiling ... [5/6] Selecting the controlled development scope ...
selected 10/10 items ... [6/6] Rendering the dataset card ...
Smoke test complete.
```

Both commands were actually run in this session (not simulated); the output
above is copied from the real run. `make smoke`'s output directory is
git-ignored and was deleted afterward (`make clean-smoke`) so it can't be
mistaken for a real dataset card.

## Findings

- **The pipeline's logic is sound** against every planted issue in the
  fixture: duplicate grain, negative/fractional values, null `onpromotion`,
  an orphan item reference, and a missing calendar date were all correctly
  detected with exact counts (see `tests/unit/test_checks.py` and
  `tests/unit/test_profile_favorita.py` for the hand-counted expected
  values).
- **[VERIFY] carried forward from Phase 00, still unverified:** the ~4.65 GB
  file size, the ~16% `onpromotion` NULL share, the `.7z` inner-archive
  format, and the exact column dtypes all came from public write-ups
  reviewed in Phase 00, not from the real files. The code is written to fail
  loudly (not silently) if any of these turn out to be wrong.
- **No findings yet about the real dataset itself** — there are none to
  report honestly, because it hasn't been profiled yet.

## Limitations

- **The real Kaggle files are unverified in this session** (§"Why the real
  run hasn't happened yet"). This is the central limitation of this phase's
  deliverable right now.
- **`docs/dataset_card.md` does not yet exist.** Creating it now with
  fixture-derived or invented numbers, and presenting it as Favorita's
  dataset card, would violate CLAUDE.md §19's honesty rule. It will be
  generated by `make dataset-card` once a real profiling run exists.
- **Every dataset limitation already identified in Phase 00** carries
  forward unchanged: no item-level pricing, no stockout/availability signal,
  "hub" simulated by "store", an Ecuadorian (not the target company's real)
  calendar — see `docs/decisions/0001-phase00-decisions-and-scope.md`.
- **The `.7z` extraction path (`_extract_nested_archives`) is untested**,
  since the fixture ships as plain CSV and no real `.7z` file exists in this
  session to test against. If the real download's archive layout differs
  from the [VERIFY] assumption, this is the most likely place a first real
  run would need a fix.

## What to review

1. **`tests/fixtures/favorita_sample/*.csv`** — confirm the planted issues
   (open `train.csv`; row 6 duplicates row 5's key, row 16 is negative, row
   19 is fractional, row 24 references item `999`, `2013-01-10` is absent).
2. **`src/demandflow/profiling/checks.py`** — the exact set of things Phase
   01 inspects; flag anything you'd want checked that isn't here yet.
3. **`src/demandflow/scope/select_dev_scope.py`** — the stratified sampling
   logic, against ADR 0001 §2's description; confirm it matches what you
   approved.
4. **`configs/project.yaml`** — the sampling parameters (10% target
   fraction, 4 volume quantiles, 5% promo threshold); these are `[DECISION]`
   values you can adjust before the real run.
5. **Run it yourself once Kaggle access is available**, per the PowerShell
   commands above, and tell me what comes back — especially whether
   `acquire_favorita.py`'s `.7z`/`.zip` handling needs adjusting.

## Interview questions

- Why does the CSV→Parquet conversion assert an explicit schema instead of
  letting DuckDB infer types, and what happens if the real file's columns
  don't match?
- Why is the development-scope sample stratified by four different axes
  instead of just taking the top-N items by volume — what evidence would a
  volume-only sample be missing?
- Why does each stratum cell get its own seeded `random.Random` instead of
  one global RNG draw across all items?
- What's the difference between what Phase 01 checks (`profiling/checks.py`)
  and what Phase 02 will do with the same kind of findings — why isn't a
  severity/handling-decision assigned here?
- Why is the dataset card generated from a JSON report instead of written by
  hand, and why does that matter for honesty about what's real vs. assumed?
- What exactly is unverified about this dataset right now, and why wasn't it
  faked to make this phase look "done"?

---

**STOP — Phase 01 as executable in this session ends here.** Per phase
discipline (CLAUDE.md §18), Phase 02 (Data Quality) has not started.
