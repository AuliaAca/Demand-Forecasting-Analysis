# DemandFlow — Retail Demand Forecasting & Planning Intelligence Platform

A portfolio project simulating the analytics workflow of a Data Analyst
supporting a demand-planning function: analyzing sales/demand patterns,
building forecasting logic, evaluating and monitoring forecast accuracy,
investigating data issues and discrepancies, and turning all of it into
automated tools and business recommendations.

> **Public-repository notice.** This project was scoped against a real
> job description for a Data Analyst role at a real quick-commerce
> company, supplied privately by the project owner. The company's name,
> exact wording, and identifying narrative are **not reproduced anywhere
> in this repository** — only an anonymized, paraphrased restatement of
> the requirement categories (`CLAUDE.md` §1). The verbatim source is
> kept locally, outside version control. This project is an
> industry-inspired simulation; it does not claim the target company's
> internal data, systems, or practices anywhere. See `CLAUDE.md` for the
> full scoping rules this project was built under.

---

## What this demonstrates

Every capability below is scoped to a specific, paraphrased requirement
from the target role profile — never invented because a technology
sounded impressive. See **`docs/phase_reports/phase16.md`** for the full,
line-by-line final audit (46 items: Position purpose, Missions,
Requirements, Bonus — each classified as Demonstrated, Partially
demonstrated, Not demonstrated, or Limited by dataset, with a cited
source phase for every claim, and explicitly **not** reduced to a score).

In short: demand pattern analysis across SKU/hub/category/campaign/
seasonal-event (pricing is the one dimension the dataset doesn't
support — documented, not fabricated); a forecasting progression from
naive baselines through statistical (intermittent-demand) methods to a
machine-learning model, each tried only where the evidence justified it;
a full evaluation → monitoring → root-cause-analysis → alerting chain;
automated SQL/Python tooling throughout, including a BigQuery SQL port
and an Airflow DAG (both validated offline — no live GCP/Kaggle access
in this environment, disclosed everywhere it's relevant); and a
decision-oriented dashboard tying it all together.

## Pipeline architecture

```
Raw Retail Data
  -> Data Validation                  (Phase 02)
  -> SQL Transformation               (Phase 03)
  -> Analytical Data Layer/Warehouse  (Phase 03)
  -> Demand Analysis                  (Phase 04)
  -> Forecasting                      (Phases 05-07)
  -> Forecast Evaluation              (Phase 08)
  -> Anomaly/Discrepancy Investigation & Root-Cause Analysis  (Phase 09)
  -> Monitoring                       (Phase 10)
  -> Alerts / Trackers                (Phase 11)
  -> Dashboard                        (Phase 14)
  -> Business Recommendations
```

Plus two cross-cutting bonus phases (Airflow orchestration, Phase 12; a
BigQuery SQL port, Phase 13) and a hardening phase (testing, CI,
reproducibility; Phase 15) that applies across the whole system rather
than adding a pipeline stage of its own.

## Dataset, and the real-data-access gap

The dataset is the [Corporación Favorita Grocery Sales Forecasting](https://www.kaggle.com/c/favorita-grocery-sales-forecasting)
Kaggle competition — chosen over alternatives (see
`docs/decisions/0001-phase00-decisions-and-scope.md`) specifically
because it covers more of the target role's named analysis dimensions
(SKU, hub/store, category, a genuine per-record promotion flag, and a
rich holiday calendar) than the alternatives considered, at the cost of
having no pricing dimension — a disclosed, accepted gap, not an oversight.

**This development environment has no Kaggle, live GCP/BigQuery, or
Looker Studio access.** Every phase was built and validated against a
small, committed synthetic fixture (`tests/fixtures/favorita_sample/`)
that mirrors the real dataset's schema, and every review package says so
explicitly rather than presenting fixture-derived numbers as real
findings. Running against the real dataset only requires Kaggle
credentials — the code itself does not change; see **Running it**, below.

## Running it

```bash
pip install -e ".[dev]"

# Full pipeline, one phase at a time (each also has its own finer-grained
# targets -- see the Makefile):
make phase01   # acquire + convert + profile + dev-scope selection + dataset card
make phase02   # data-quality rule catalog + report
make phase03   # build the SQL warehouse
make phase04   # exploratory demand analysis + report
make phase05   # naive / seasonal-naive baselines
make phase06   # statistical (intermittent-demand) models
make phase07   # ML (LightGBM) forecasting
make phase08   # forecast evaluation by segment/horizon
make phase09   # root-cause analysis (data issues + forecast discrepancies)
make phase10   # monitoring signals
make phase11   # alerts + discrepancy tracker
make phase12   # Airflow DAG validation (needs `make airflow-install` first)
make phase13   # BigQuery SQL validation (offline, no GCP project needed)
make phase14   # decision-oriented dashboard -> docs/dashboard.html
make phase15   # lint + full test suite (same as CI)

# Or: run the whole thing end-to-end against the committed fixture in one
# command, proving the pipeline's plumbing without needing real data:
make smoke

# Development:
make test      # full test suite
make lint      # ruff
```

Every `make` target is a thin wrapper over a plain `python -m ...` call —
see each target's recipe in the `Makefile`, or the equivalent commands in
each phase's own `docs/phase_reports/phaseNN.md`, if `make` isn't
available.

## Repository map

| Path | What's there |
|---|---|
| `CLAUDE.md` | The project's persistent context: the anonymized target-role profile (source of truth for scope), the JD→capability→evidence framework, and the phase-by-phase implementation rules this project was built under. |
| `docs/00_requirement_analysis_and_system_plan.md` | Phase 00's full requirement analysis and system design — the plan every later phase executes against. |
| `docs/decisions/` | Architecture decision records (dataset selection, scope trade-offs). |
| `docs/phase_reports/phaseNN.md` | One review package per phase (16 total) — what was built, which exact JD requirement it evidences, key decisions, validation actually run, findings, limitations, and interview questions. **`phase16.md` is the final audit.** |
| `src/demandflow/` | All pipeline code, organized by phase concern (`ingest/`, `quality/`, `transform/`, `analysis/`, `forecasting/`, `evaluation/`, `rca/`, `monitoring/`, `alerts/`, `bigquery/`, `reporting/`). |
| `sql/` | Layered SQL models (staging → intermediate → marts) for both DuckDB (the primary warehouse) and the BigQuery-dialect port. |
| `dags/` | The Airflow DAG (Phase 12), isolated from the main Python environment (`requirements-airflow.txt`, `.venv-airflow/`, both git-ignored/separate for a reason explained in `docs/phase_reports/phase12.md`). |
| `tests/` | Unit and integration tests (353+ at last count — see `docs/phase_reports/phase15.md`), plus the small committed fixture every phase validates against. |
| `.github/workflows/ci.yml` | Lint + full test suite on every push/PR, against the fixture (Phase 15). |
| `configs/project.yaml` | The single source of project-level configuration (random seed, forecasting horizon/cadence, dev-scope sampling parameters) — all `[DECISION]`/`[ASSUMPTION]` project choices, not JD figures. |

## A note on process

This project was built iteratively, phase by phase

---

**Where to start:** `docs/phase_reports/phase16.md` (the final audit) for
the honest, evidence-cited summary of what this project does and doesn't
demonstrate; `CLAUDE.md` §1 for the anonymized role profile everything
here is scoped against.
