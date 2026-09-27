# Phase 15 — Testing & Reliability: Review Package

**Phase objective (from the Phase 15 prompt):** strengthen testing,
validation, reliability, reproducibility, logging, configuration, and
failure handling across the system. Check that implemented evidence still
maps correctly to the exact JD.

**Status: six concrete, verified hardening changes across the codebase —
not a token "add more tests" pass. Every claim below was actually run in
this session, the same discipline as every previous phase.**

---

## What was built

| Area | Change |
|---|---|
| **Reliability / failure handling** | All 14 non-`build_warehouse` DuckDB `connect()` call sites across 12 modules converted from manual `connect()`/`close()` to `with duckdb.connect(...) as con:`. This is not cosmetic: four of them (`run_backtest.py`, `run_statistical_backtest.py`, `run_ml_backtest.py`, `run_evaluation.py`) had a real connection leak — each raised `ValueError` on an empty `fct_sales_daily` *before* its own `con.close()` ever ran. `build_warehouse.py` is the one deliberate exception: it returns the open connection to its caller by design, and every caller already closes it. |
| **Reproducibility** | `src/demandflow/forecasting/ml.py`: LightGBM's `DEFAULT_PARAMS` had no `random_state` — two identical `train_model()` calls were not guaranteed to produce identical predictions. Added `random_state=42` (matching `configs/project.yaml`'s existing `random_seed`), `deterministic=True`, `force_row_wise=True` — LightGBM's own documented requirement for bit-for-bit reproducible runs. |
| **Configuration validation** | `src/demandflow/config.py`: `load_config()` previously did zero validation past "file exists" — a missing section raised a bare `KeyError`, and an out-of-range value (e.g. negative `horizon_days`) loaded silently and failed later, deep inside whichever phase used it first. Added a new `ConfigError` exception, section-presence checks, and range checks (`random_seed >= 0`, `forecasting.*` all positive integers, `dev_scope.target_item_fraction`/`promo_intensity_threshold` in `(0, 1]`). `config.py` had **zero** direct unit tests before this phase. |
| **CI** | `.github/workflows/ci.yml`: lint (`ruff`) + full test suite on every push/PR, entirely against `tests/fixtures/favorita_sample/` — no Kaggle/GCP credentials needed. This closes a gap named explicitly in Phase 00's own plan (`docs/00_requirement_analysis_and_system_plan.md`: *"Phase 15: testing and reliability (CI, idempotent runs, end-to-end smoke test on fixtures)"*) that had not yet been built. |
| **Lint** | `ruff` added to the `dev` extra (`pyproject.toml`, default rule set only — unused imports/names, undefined names; no style opinion imposed across 14 already-reviewed phases). 8 pre-existing issues (7 unused imports, 1 redundant f-string prefix) found and fixed; `ruff check src/ tests/` now passes clean. `make lint` and `make phase15` (`lint` + `test`) added to the `Makefile`, mirroring exactly what CI runs. |
| **End-to-end smoke test + idempotency** | New `tests/unit/test_end_to_end_smoke.py` (3 tests): (1) chains every phase's real `run_and_write()` — EDA, three backtest variants, evaluation, RCA, monitoring, alerts — on one shared warehouse in one continuous run, something no existing test file did (each phase's own tests rebuild their own warehouse in isolation); (2) confirms a second alerts run advances `run_seq` cleanly (the one deliberate exception to "rebuild, don't accumulate" — `monitoring_history` is append-only by design); (3) rebuilds the warehouse twice from the same fixture and confirms `fct_sales_daily`'s row count and Phase 08's evaluation numbers are bit-identical both times — the actual idempotency claim, not just "it ran without error." |
| **New unit tests elsewhere** | `test_train_model_is_deterministic_across_repeated_calls` (`tests/unit/test_ml.py`) — two `train_model()` calls, identical inputs, asserts bit-identical predictions. `test_run_and_write_releases_the_connection_when_the_warehouse_is_empty` (`tests/unit/test_run_evaluation.py`) — proves the connection-leak fix for real: after the early `ValueError`, a fresh `duckdb.connect()` to the *same file* is attempted immediately; DuckDB's single-writer file lock means this would fail if the previous connection had leaked. `tests/unit/test_config.py` — 22 new tests for `load_config()`'s validation behavior (missing sections, missing keys, out-of-range values, a real load of the repository's own `project.yaml`). |

**Total test count: 353 passed + 1 skipped** (up from 326 + 1 — the skip
is still Phase 12's Airflow-only file, which needs the isolated
`.venv-airflow` environment).

---

## JD connection

| What this phase provides evidence for | JD reference |
|---|---|
| **"...and reliability"** — the position's own stated objective, not just accuracy. Connection-handling hardening (no leaked resources on an error path) and CI (a rerun on every push actually verifying the pipeline still works, not just once in this session) are both direct evidence of reliability engineering, not accuracy work. | Position purpose ("demand forecast accuracy and reliability"); CLAUDE.md §20 (RO-2) |
| **Reproducibility** — the LightGBM determinism fix directly serves the "rebuild, don't trust a stale file" principle every phase since Phase 08 depends on: if the ML model could produce different predictions from identical inputs run to run, that principle would be undermined for exactly the one model that needed it. | CLAUDE.md §14 (engineering principles: reproducibility); mission "improve forecasting logic" |
| **"SQL, Python... to transform data and automate repetitive processes"** — CI is automation of a repetitive process (running the test suite) using the project's own Python/pytest tooling, on every push, without manual effort. | Missions; CLAUDE.md §14 |
| **"Strong analytical and problem-solving skills with attention to detail"** — the four real connection leaks and the config module's total lack of prior tests were found by re-reading each file's actual control flow, not by a test failure; the LightGBM fix was verified against the existing hand-verified WAPE number rather than assumed safe. | Requirements (R-6) |
| **Investigate data issues... root-cause analysis (methodology, not this phase's subject)** — not directly this phase's target, but the new idempotency test extends the same "verify, don't assume" discipline RCA (Phase 09) established to the pipeline's own rebuild behavior. | CLAUDE.md §3.6 (indirect) |
| **"Git" bonus exposure** | A working CI workflow, wired to run on every push/PR, is concrete evidence of Git-based automation, not just `git commit` usage. | CLAUDE.md §5 (bonus) |

**JD-mapping spot-check (this phase's other explicit ask):** grepped every
`docs/phase_reports/*.md` for overclaiming language (`proves`,
`guarantee[sd]`, `equivalent to N years`, claims of real cross-team
collaboration, claims the years-of-experience requirement is satisfied).
Every match found is either (a) about a *test* proving something about
*code* (e.g. "a leakage guarantee can be proven directly on" pure
functions — a true statement about pytest, not about the target role) or
(b) already correctly hedged (Phase 02's cross-functional routing note
explicitly says "simulated perspective... not real collaboration"). No
drift found between what's built and what CLAUDE.md §1 actually states.
The standard leak-sweep grep (real company name/identity markers) is also
clean except the one known, intentional Airflow-vendor-name disambiguation
note in `docs/00_requirement_analysis_and_system_plan.md` — unchanged
since Phase 12.

---

## Key decisions

- **Scope: concrete, verifiable gaps, not a vague "add more tests"
  pass.** Each change above fixes something specific and demonstrable
  (a real leak, a real missing-seed gap, a real missing-test-file, a real
  plan-doc gap), rather than padding coverage on already-well-tested
  code. CLAUDE.md §14: "Do not over-engineer."
- **`with duckdb.connect(...) as con:` everywhere except
  `build_warehouse.py`.** That one function is a documented exception —
  it returns the open connection to its caller by contract, and every
  caller across the codebase already closes it correctly. Converting it
  too would break that contract for no reliability gain.
- **LightGBM's seed is a literal `42` in `ml.py`, not threaded through
  `cfg.random_seed`.** `ml.py` has no other reason to import `config` —
  every existing caller (`run_ml_backtest.py`, both test files) calls
  `train_model()` with no seed argument, so baking the constant directly
  into `DEFAULT_PARAMS` required zero call-site changes anywhere. The
  value `42` was chosen to match `configs/project.yaml`'s
  `random_seed: 42` for narrative consistency, not because `ml.py` reads
  that config.
- **Verified the LightGBM fix against the existing pinned number, not
  around it.** `test_ml_backtest.py`'s hand-verified holdout WAPE for
  `lightgbm` (`0.8246904469327779`, from Phase 07) was a real risk of
  shifting once `deterministic=True` was added. It did not shift — this
  was actually re-run and checked, not assumed, per CLAUDE.md's
  hand-verify discipline (the number would have been honestly re-derived
  and re-pinned had it changed, never adjusted to force a pass).
  `test_train_model_is_deterministic_across_repeated_calls` now pins the
  new guarantee explicitly, rather than relying on that older test's
  passing coincidentally proving determinism.
  Determinism is a per-process guarantee for CPU LightGBM with these
  settings (single-machine, fixed thread behavior) — this project makes
  no claim about cross-machine or cross-LightGBM-version bit-identical
  reproduction.
- **CI runs lint + test against the fixture only, same as every other
  phase's own validation.** No Kaggle, GCP/BigQuery, or Looker Studio
  credentials are configured or used — this is the exact same real-data
  gap disclosed since Phase 01, now made structurally impossible to
  route around in CI (there is nothing else for CI to run against).
- **`ruff`'s default rule set only, not a full style/format gate.**
  Catches real bugs (unused imports, undefined names) without imposing a
  new formatting opinion retroactively across 14 already-reviewed
  phases' worth of code. The 8 pre-existing issues found were fixed
  directly (all safe, auto-fixable, semantics-preserving — confirmed by
  diff review, e.g. the one f-string fix was a redundant `f` prefix with
  no placeholders, not a logic change).
- **The end-to-end smoke test re-asserts as few numbers as possible.**
  Its job is to prove the phases are wired together and idempotent, not
  to duplicate the detailed, hand-verified assertions every phase's own
  test file already carries — light sanity checks (`champion_model is
  not None`, `len(signals) == 4`) rather than pinned floats, except
  where idempotency is the literal thing being tested (there, the
  numbers must match exactly, by definition).
- **Dashboard/report-generation layer intentionally excluded from the
  smoke test.** It reads from `reports/phaseNN/*.json` paths on disk
  rather than the warehouse directly, and every report generator already
  has its own dedicated test file (`test_generate_*_report.py`,
  `test_generate_dashboard.py`) — wiring it into this test would
  duplicate coverage that already exists elsewhere, not add new evidence.

---

## Validation

```
$ ruff check src/ tests/
All checks passed!

$ python3 -m pytest tests/ -q
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 61%]
........................................................................ [ 81%]
.................................................................        [100%]
353 passed, 1 skipped in 201.45s (0:03:21)
```

Both commands were actually run in this session (the second one twice —
once immediately after the connection-handling refactor alone, confirming
no regression before moving on to the next change, and again as the final
check with every Phase 15 change in place).

Targeted checks also run and inspected directly:

- `tests/unit/test_ml.py` and `tests/unit/test_ml_backtest.py` re-run
  immediately after the LightGBM determinism change, specifically to
  check whether the pinned holdout WAPE number shifted. It did not.
- `tests/unit/test_end_to_end_smoke.py` run standalone (`-v`) to confirm
  all three tests pass individually, in ~18s.
- `make lint` run directly to confirm the new Makefile target matches
  what `.github/workflows/ci.yml` runs.

---

## Findings

- **Four real DuckDB connection leaks existed on early-raise error
  paths** in Phases 05–08's backtest/evaluation entrypoints — not
  hypothetical, not caught by any existing test (none of them exercised
  the empty-warehouse path), found only by re-reading each file's actual
  connect/close control flow against Phase 15's own "failure handling"
  objective.
- **LightGBM (Phase 07's ML model) had no fixed random seed** despite
  the project's own `configs/project.yaml: random_seed: 42` convention
  existing elsewhere and being used by `select_dev_scope.py` — a real,
  specific reproducibility gap, not a generic one.
- **`config.py` — the module every single phase depends on to even
  start — had zero direct unit tests before this phase**, and its
  `load_config()` gave no validation beyond "the YAML file exists."
- **Phase 00's own system plan had already named CI, idempotent runs,
  and an end-to-end smoke test as this phase's job**
  (`docs/00_requirement_analysis_and_system_plan.md`), and none of the
  three existed yet — this was checked directly against the plan
  document, not just against the (looser) Phase 15 prompt text, per
  CLAUDE.md §18's instruction to document rather than silently skip
  planned-but-not-yet-built work.
- **The JD-mapping spot check found no drift** between what's actually
  built and CLAUDE.md §1's paraphrased source — every "proves"/
  "guarantee" occurrence in the phase reports refers to test code
  proving something about the code, never a claim about real-world
  forecast performance or real professional experience.

## Limitations

- **CI has never actually executed on GitHub** in this sandbox session —
  there is no GitHub Actions runner available here to trigger it against.
  Its correctness was validated by confirming, directly, that every
  command it runs (`pip install -e ".[dev]"`, `ruff check src/ tests/`,
  `pytest tests/ -q`) succeeds from a clean environment locally; the
  workflow YAML itself should still be watched on the first real push.
- **Determinism is scoped to this machine/LightGBM version.** `42` +
  `deterministic=True` + `force_row_wise=True` guarantees repeat runs
  produce identical output *here*; it is not a claim of bit-identical
  output across different hardware, thread counts, or LightGBM versions
  (LightGBM's own documentation is explicit that `deterministic=True`
  addresses feature-parallel/threading nondeterminism specifically, not
  every possible source of numeric variation).
- **The end-to-end smoke test still only proves the pipeline is wired
  together and idempotent on the small fixture** — the same real-data
  gap every phase has disclosed since Phase 01 (no Kaggle access in this
  sandbox). It is not evidence the pipeline behaves the same way at the
  real dataset's scale.
- **Config validation covers range/presence checks only**, not
  cross-field consistency (e.g. it does not check that
  `min_history_days <= forecasting.horizon_days` or similar semantic
  relationships between sections) — `backtest.py`'s own
  `generate_as_of_dates()` still independently guards
  `min_history_days >= 1` at the point of use, so this is a
  defense-in-depth addition, not the only guard.
- **Logging was reviewed, not changed.** Every module with a logger
  follows the same pattern (`logger = logging.getLogger(__name__)`,
  `logging.basicConfig()` only in each file's own `_main()`) already;
  the two files that call `basicConfig()` without defining their own
  module-level logger (`quality/rules.py`, `scope/select_dev_scope.py`)
  do so because their `_main()` uses `print()` for CLI output and
  `basicConfig` only configures logging for any imported code that does
  log — this is intentional, not an inconsistency, so no change was
  made.

## What to review

1. **`src/demandflow/forecasting/ml.py`** — the three new LightGBM
   parameters and the reasoning comment above `DEFAULT_PARAMS`.
2. **`src/demandflow/config.py`** — the new `ConfigError` class and
   validation logic, especially whether the chosen range checks
   (e.g. `target_item_fraction` must be in `(0, 1]`) match your own
   intuition for what "invalid" should mean here.
3. **`.github/workflows/ci.yml`** and the `[tool.ruff]` section in
   `pyproject.toml` — confirm you're comfortable with this being the
   repository's first CI workflow, and with the default-rules-only lint
   scope.
4. **`tests/unit/test_end_to_end_smoke.py`** — particularly
   `test_rebuilding_the_warehouse_is_idempotent`, the phase's most
   direct evidence for the "idempotent runs" item named in Phase 00's
   plan.
5. **The 12-file DuckDB connection-handling diff** (`git diff` against
   any file in the "reliability / failure handling" row above) —
   confirm the `with` conversions read correctly, especially
   `build_warehouse.py`, which was deliberately left unconverted.

## Interview questions

- Walk through one of the four real connection leaks you found — what
  was the exact code path that skipped `con.close()`, and how did you
  confirm your fix actually closes it (rather than just looking
  correct)?
- Why does `build_warehouse.py` deliberately keep its connection open
  and return it to the caller, instead of also using a `with` block —
  what would break if you converted it?
- What specifically does `deterministic=True` guarantee in LightGBM, and
  what does it *not* guarantee? Why did you choose `42` as the seed
  value, and why isn't it read from `configs/project.yaml`?
- You added 22 tests for `load_config()` alone. What made this module a
  priority given every other module in the codebase already had test
  coverage?
- What's the difference between what `test_end_to_end_smoke.py` proves
  and what each phase's own existing tests already proved? Why did
  neither approach make the other redundant?
- The idempotency test rebuilds the warehouse twice and checks the
  evaluation numbers match exactly. What would it mean, diagnostically,
  if they didn't — what's the first thing you'd suspect?
- Why did you add CI now, in Phase 15, rather than in Phase 01 when the
  test suite first existed? Was that the right call?

---

**STOP — Phase 15 ends here.** Per phase discipline (CLAUDE.md §18),
Phase 16 (Portfolio Polish & Final Audit) — the last phase in CLAUDE.md
§17's list — has not started.
