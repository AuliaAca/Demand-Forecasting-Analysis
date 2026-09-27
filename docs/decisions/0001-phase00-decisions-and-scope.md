# ADR 0001 — Phase 00 Finalized Decisions, Controlled Development Scope, and Critical Reassessment

**Status:** Accepted (all items, including hardware sizing — see §4).
**Date:** 2026-09-27 (hardware sizing closed 2026-09-27)
**Deciders:** project owner, reviewing the Phase 00 plan in [`docs/00_requirement_analysis_and_system_plan.md`](../00_requirement_analysis_and_system_plan.md).
**Still true:** no dataset has been downloaded and no implementation code has been written. This ADR closes out Phase 00 decision-making; it does not start Phase 01.

---

## 1. Decisions finalized

| ID | Decision | Final position |
|---|---|---|
| D1 | Primary dataset | **Favorita**, confirmed. Subject to a controlled development scope (§2) rather than processing the full ~125M rows from day one. |
| D2 | Pricing gap | **Accepted as a documented "Limited by dataset" gap.** No second pricing dataset for now. Revisit only if pricing becomes a stated priority later. |
| D3 | Grain / horizon / cadence | **store × SKU × day, 14-day horizon, weekly as-of runs.** Confirmed as a **[DECISION/ASSUMPTION]**, not a JD requirement — the target JD does not specify a horizon or cadence. |
| D4 | Modelling scope | Superseded by the controlled development scope in §2. |
| D5 | Local stack | Python + DuckDB + Parquet — confirmed. |
| D6 | SQL framework | Plain layered SQL, no dbt — confirmed. |
| D7 | BigQuery mode | Sandbox (free, no card, 60-day table expiry, no DML) for development — confirmed. |
| D8 | Dashboard tool | Looker Studio, with a local generated report as the MVP fallback — confirmed. |
| D9 | Airflow | **Optional**, decided only after the MVP (Phases 00–11) is working, and only if it adds evidence beyond what the CLI + Makefile already demonstrate. Default lean is **not to build it** unless there is spare time — see §5, item A2. |
| D10 | Where the pipeline runs | **Locally, on the project owner's Windows laptop, working from the `D:` volume.** Confirmed sufficient — see §4. Raw data and large processed data will not be pushed to GitHub under any outcome. |
| D11 | Public repository contents | **Resolved.** `CLAUDE.md` has been rewritten as an anonymized, paraphrased restatement of the target JD (no company name, no verbatim marketing copy, same requirement categories). The verbatim original is kept at `.private/JD_SOURCE_VERBATIM.md`, which is git-ignored and has never been committed. `docs/00_requirement_analysis_and_system_plan.md` has been scrubbed of the company name and identifying details (country, founding year, tagline) for the same reason. See §6. |

---

## 2. Controlled Development Scope — sampling methodology for Favorita

**Goal:** develop and validate the full pipeline on a small, defensible, reproducible subset of Favorita, then treat scaling to more of the data as a separate, later, optional step — never a precondition for finishing the project.

### 2.1 What stays full-size

The dimensions the JD explicitly asks us to analyze are **not** subsetted, because keeping them intact is what lets DemandFlow answer the JD's questions, and none of them is what drives the 125M row count:

- **All 54 stores** (hubs) — dropping stores would directly weaken the one JD dimension ("hubs") that Favorita represents most literally.
- **The full date range** (~2013–2017) — a shorter window would break exactly the multi-year trend/seasonality/holiday evidence (M-2a, M-2b, M-1f) that is one of Favorita's main strengths over the alternatives.
- **All reference tables** (`stores`, `items`, `holidays_events`, `oil`, `transactions`) — these are already small (thousands of rows, not millions).

### 2.2 What is subsetted, and how

**Only the SKU (item) dimension is reduced**, because `train.csv`'s row count is driven by the store × item × day cross-product (minus omitted zero-sales rows), and item count (~4,100 [VERIFY]) is the one axis we can shrink without touching a JD-named dimension.

The selection is **stratified**, not arbitrary, on four axes computed from the real data during Phase 01 profiling:

1. **`family` and `class`** (Favorita's own category hierarchy) — so every product category the JD's "categories" dimension could be tested against remains represented, not just the biggest ones.
2. **`perishable` flag** — so the perishable/non-perishable split that RO-6's under/over-forecast risk framing depends on survives the sample.
3. **A volume tier**, computed from each item's total historical `unit_sales` (e.g., quartiles or deciles within its family) — so fast movers, medium movers, and slow/intermittent movers are all present. Sampling only top sellers would quietly delete the intermittent-demand and demand-anomaly evidence (M-2c, M-2d) the JD explicitly asks for.
4. **A promotion-intensity flag** (share of days each item appears with `onpromotion = True`) — so items with a real promotion history are not diluted away, preserving evidence for M-1d.

Within each stratum cell, a fixed proportion is drawn using a **fixed random seed**, targeting an initial scope of roughly **8–15% of items** (the exact figure is set in Phase 01 once real strata sizes are known — not decided blind here). At that ratio, expected row counts land in the low tens of millions rather than 125M, which is comfortably within local, single-machine, columnar processing (see §4).

### 2.3 Validation of the sample (not just selection)

Before the sample is treated as the development scope, Phase 01 will check that it is not distorted:

- Compare the **aggregate weekly/monthly sales seasonality shape** of the sample against the full catalog.
- Compare **promotion-lift and holiday-lift** patterns (the ratio of on-promotion/holiday sales to baseline) between sample and full catalog.
- If either diverges materially, strata weights are adjusted before the scope is frozen.

This validation step is itself evidence for the JD's "attention to detail" requirement (R-6) — it is what separates a defensible sample from an arbitrary one.

### 2.4 Freezing and reproducibility

The exact item list, the selection SQL, and the random seed are committed as a small artifact (e.g. `configs/dev_scope_items.csv` plus the selection query that produced it). Given it is only a few hundred to ~1,000 item IDs, this is a legitimate, lightweight, committable file — not raw data.

### 2.5 Data lifecycle (what touches the full 125M rows, and what doesn't)

| Step | Scope | Where it runs |
|---|---|---|
| Download and checksum | Full raw files | Local, one-time |
| Profiling (row counts, null shares, key uniqueness, strata sizing) | **Full** `train.csv` | Local, via DuckDB reading the CSV directly — DuckDB does not need the file to fit in RAM, so this step alone is real evidence of working with a large dataset (R-2b) without needing a large machine |
| Item-selection query | Full `train.csv` (to compute the strata), output is the small frozen item list | Local, one-time |
| Raw → Parquet conversion | Full data converted once (kept locally only, never committed); this is what a later scale-up step (§2.6) would reuse | Local, one-time |
| Staging → intermediate → marts → forecasting → evaluation → monitoring → RCA (Phases 02–11) | **Scoped subset only** | Local, iterative |
| Optional scale-up check | A larger sample or the full dataset | Local (if resources allow) or BigQuery (§2.6) — not required for the MVP |

### 2.6 Optional later scale-up (not part of the MVP)

Once the pipeline works end-to-end on the scoped subset, the *same, unmodified* pipeline can optionally be re-run against a larger sample or the full dataset — most sensibly in BigQuery rather than on a laptop — and the runtime/bytes-processed compared against the local scoped run. **This is what actually demonstrates the JD's "scalable solutions" requirement (M-7e)**, more convincingly than brute-forcing 125M rows locally would: it shows the pipeline was designed so scope is a parameter, not a rewrite. This step is explicitly optional and deferred; it is not required to consider the project finished.

### 2.7 How this affects validity and portfolio value

**It does not weaken the project's validity, provided it is disclosed — and disclosure is non-negotiable.**

- Every dataset card, EDA notebook, evaluation report, and the final README must state plainly that development-phase results (backtested accuracy, EDA findings, RCA case studies) are computed **on the documented development scope**, not the full Favorita catalog, and must link to the sampling methodology above.
- This is, if anything, a **stronger** signal for a Data Analyst / Analytics Engineering portfolio than "I ran it on all 125M rows," because:
  - Developing and iterating on a representative, principled subset before scaling is how real analytics teams actually work — it is a cost- and time-management skill the JD implicitly expects ("fast-paced environment," "scalable solutions" without implying "always use maximum data").
  - A **stratified, validated, reproducible** sample is itself a demonstrable skill (sampling design, bias awareness, reproducibility) that an arbitrary "first 10 stores" subset would not show.
- The genuine limitation to be honest about: metrics measured on ~10% of items are not guaranteed to generalize identically to the other 90%, especially the very long tail of rare/intermittent items not covered by the sample's slow-mover stratum. The validation step in §2.3, and the optional scale-up in §2.6, are the mitigations — not a claim that the risk is eliminated.
- **Net assessment:** validity is preserved *for the claims the project actually needs to make* (forecasting method comparison, evaluation methodology, monitoring/alerting/RCA workflow design). It would not be preserved if the project quietly implied "these accuracy numbers describe Favorita's whole catalog" — so the plan requires that it never does.

---

## 3. Anonymization confirmation (D11)

Concrete state as of this ADR:

- `CLAUDE.md` §1 is now titled "Target Role Profile — Anonymized Source of Truth." It paraphrases the company background, position, missions, requirements, and bonus points without naming the company, without reproducing its marketing copy verbatim, and without its country or founding-year details. All working-rule sections (§2–§20) now refer to "the target role" / "the target company" instead of the company's name.
- The verbatim original — the exact text supplied by the project owner — is at `.private/JD_SOURCE_VERBATIM.md`, which is listed in `.gitignore` and has not been, and will not be, committed.
- `docs/00_requirement_analysis_and_system_plan.md` has been edited to remove the same identifying details (company name, country, founding year, delivery-time tagline) everywhere they appeared, while preserving every substantive JD-to-project mapping.
- Going forward, no file committed to this repository should name the target company. If a future phase's output would need to, stop and ask first.

---

## 4. Hardware and resource assessment (D10)

### 4.1 What the numbers look like [VERIFY — public estimates, to be confirmed in Phase 01]

- `train.csv` alone is reported at roughly **4.65 GB** uncompressed (125,497,040 rows × 5 columns). The other files (`stores`, `items`, `holidays_events`, `transactions`, `oil`) are each a few thousand rows and add only low tens of MB combined.
- **Disk, one-time peak** (download + a full Parquet re-encode, before anything is deleted): raw CSV (~5 GB) + full raw Parquet copy (likely ~1–1.5 GB, columnar encoding compresses this kind of repetitive numeric/date data well) + tooling/environment overhead. **Recommend at least 15 GB free disk** for this step; **20–25 GB** if you want to keep the full raw Parquet around locally to support the optional scale-up check in §2.6 instead of re-downloading later.
- **Disk, ongoing** (scoped subset only — staging through marts, the DuckDB warehouse file, reports): well under a few hundred MB to low single-digit GB. Not a concern once the scope is frozen.
- **RAM, one-time step** (profiling and converting the *full* `train.csv`): this must go through **DuckDB** (or an equivalent chunked/streaming reader), never a naive `pandas.read_csv()` on the whole file — pandas' typical 5–10× memory multiplier would put a naive load in the 25–45 GB RAM range, which is not realistic for a laptop. DuckDB processes larger-than-RAM data by spilling to disk, so this one-time step is workable on **8 GB RAM**, more comfortable on 16 GB.
- **RAM, ongoing** (the scoped subset, ~10–15 million rows once selected): trivial — comfortably fits in memory even as a plain pandas DataFrame, on any machine with 8 GB RAM or more.

### 4.2 Recommendation

| Tier | RAM | Free disk | Verdict |
|---|---|---|---|
| Minimum | 8 GB | 15 GB free | Workable, but the full-data ingestion step **must** use DuckDB/streaming, not plain pandas, and you should not run much else at the same time during that one-time step. |
| Comfortable | 16 GB | 20–25 GB free | No special care needed; full-data ingestion and ongoing scoped-subset work both run without tuning. |

### 4.3 Confirmed against the project owner's actual machine — 2026-09-27

Reported specs (Windows laptop, two volumes):

| Volume | Free | Total | % used |
|---|---|---|---|
| `C:` (Windows system drive) | 59.6 GB | 374 GB | ~84% used |
| `D:` ("New Volume") | 84.0 GB | 99.9 GB | ~16% used |

**Verdict: sufficient, against both the minimum and comfortable disk tiers in §4.2.** Both volumes individually clear the 15–25 GB requirement, but they are not equivalent choices:

- **`C:` is already ~84% full** (only 59.6 GB free out of 374 GB). It is also the Windows system drive. Temporarily writing a ~5 GB raw CSV plus a ~1–1.5 GB Parquet copy there is technically within budget, but pushes an already-tight system drive tighter, with less headroom left over for normal OS/application use, OS updates, or the optional larger scale-up sample in §2.6.
- **`D:` has far more headroom, both in absolute free space (84.0 GB) and as a share of the volume (84% free).** It is a secondary data volume, so filling several GB there carries no system-stability risk.

**Decision: the whole project — code and data alike — should live under `D:`** (e.g. `D:\dev\Demand-Forecasting-Analysis`), not split across drives. This keeps `.gitignore`-covered data directories (raw downloads, the Parquet copy, the DuckDB warehouse file) off the nearly-full system drive entirely, and leaves 80+ GB of comfortable room — enough for the scoped-subset workflow many times over, and enough to also keep a full raw Parquet copy locally if the optional scale-up check (§2.6) is ever run.

RAM was not reported. It does not change the verdict: the plan already mandates DuckDB (never a naive `pandas.read_csv()` on the full file) specifically because that one-time full-data step is disk-spillable and not RAM-bound (§4.1). If the machine's RAM later turns out to be unusually low (well under 8 GB), that would only affect how comfortably other applications can run at the same time as that one-time ingestion step — it would not block the approach.

**D10 is closed. Disk is sufficient on `D:`. No blocker remains on hardware.**

---

## 5. Critical reassessment

Answering each point you asked about directly. **A = strongly recommended change, B = optional improvement, C = already reasonable, no change.**

### 5.1 Is Favorita still a good fit compared with M5? — **(C)**

Yes, and the pricing gap doesn't change that verdict. Favorita's advantages over M5 for *this* JD are concentrated exactly where the JD puts weight:

- **Data quality / RCA (M-6):** Favorita is genuinely messy — omitted zero-sales rows, ~16% missing `onpromotion`, negative returns, a documented earthquake shock, no Christmas rows. M5 is comparatively clean and heavily pre-studied. Since "investigate data issues," "forecast discrepancies," and "root-cause analysis" are explicit missions, Favorita gives more real material to investigate, not manufactured problems.
- **Campaigns (M-1d):** Favorita has an explicit `onpromotion` flag per item × store × day. M5 has no promotion flag at all — promotions there can only be *inferred* from price drops, which is a weaker, indirect signal for a JD line that names "campaigns" as its own dimension.
- **Hubs (M-1b):** 54 stores vs. M5's 10 gives more network breadth to talk about "hubs" plurally.
- M5's real advantage — **pricing (M-1e)** — is one of six named dimensions, but it's the "analyze patterns across" list, not a "you must build a price-elasticity model" instruction. Losing it is a real, disclosed gap, not a fatal one.

Net: Favorita's edge on campaigns, hubs, and (especially) genuine data-quality/RCA material outweighs M5's pricing advantage, given the JD's emphasis. Keep Favorita.

### 5.2 Is the controlled-development approach technically credible? — **(C)**, with **(A)** on execution discipline

Credible in principle, and I'd defend it in an interview as better practice than brute-forcing all 125M rows on a laptop — see §2.7. The one thing I'd insist on, not as a scope change but as an execution requirement for Phase 01:

- **(A) Strongly recommended:** the stratification must actually be multi-axis (family × class × perishable × volume tier × promotion intensity), with a fixed seed and a committed item list, and it must include a validation check (§2.3) comparing sample vs. full-catalog seasonality/lift shape. A single-axis "top N by volume" sample would quietly delete the intermittent/long-tail evidence the JD's "outliers" and "demand anomalies" lines are asking about, and would be much weaker to defend under questioning. This is already written into §2 above — flagging it here so it's not lost when Phase 01 starts.

### 5.3 Is store × SKU × day appropriate? — **(C)**

Yes. It's the dataset's native grain, matches "SKU" and "hub" directly, and is the standard grain for a replenishment-adjacent forecasting use case. No objection.

### 5.4 Are 14 days and weekly runs reasonable? — **(C)**, with **(B)** optional

Both reasonable defaults. One optional refinement:

- **(B) Optional:** don't just report one aggregate accuracy number across the 14-day horizon — report accuracy **by horizon day** (1, 7, 14, etc.) explicitly. The JD specifically asks "where is forecast accuracy deteriorating," and a per-horizon-day degradation curve answers that far more directly than a single blended metric. This falls out naturally from the `as_of_date` + `horizon` design already in the plan (§6.2 of the Phase 00 doc) — it just needs to be an explicit, named output, not an incidental byproduct.

### 5.5 Is the pricing limitation significant? — **(C)** accept it now, **(B)** optional later

On paper it's "1 of 6 named dimensions," so it should never be silently omitted from the final audit. In practice, it doesn't block the JD's core, higher-weighted asks (forecast accuracy, monitoring, RCA, automation), which don't depend on price data. Accepting it as a documented limitation now, with no second dataset, is the right call for a finishable project. If time remains after the core phases, a small, clearly-labeled bolt-on (e.g., a short elasticity note using M5's `sell_prices` on a handful of comparable items) would be a reasonable **(B)** — but only as an appendix, never blended into the main Favorita narrative, and only per your existing instruction to reconsider this later.

### 5.6 Is anything important missing? — **(A)** one addition, **(B)** one minor addition

- **(A) Strongly recommended:** the plan already includes a recommendations log and a discrepancy tracker (good), but "turning findings into actionable recommendations" (M-3b) is one of the most business-facing, interview-relevant lines in the JD. I'd insist Phase 09 produce **at least 2–3 fully worked, end-to-end recommendation narratives** (finding → evidence → a concrete, quantified action → expected effect), not just tooling that *could* hold recommendations. This isn't new scope — Phase 09 is already planned — it's a depth requirement on a phase that already exists, so it doesn't get diluted into generic tracker rows with no worked examples.
- **(B) Optional:** since "store" stands in for "hub" throughout, a single reusable caveat line/template used consistently across every dashboard, report, and notebook (rather than restating it ad hoc each time) would keep that disclosure consistent without extra work.

I don't see any JD-required capability with zero planned coverage.

### 5.7 Is anything unnecessarily complex and should be cut? — **(A)** two defaults to tighten

- **(A) Strongly recommended:** default to **not building the Airflow DAG at all** unless there is spare time after the MVP is done and reviewed. It's a bonus-only item, the CLI + Makefile already demonstrates automation (M-5d), and adding Docker + a scheduler is real infrastructure weight for a signal that's already covered another way. (This matches your own "optional, only if it adds value" instruction — I'm just recommending the default outcome be "skip it" rather than leaving it open-ended.)
- **(A) Strongly recommended:** keep the ML forecasting phase (07, LightGBM) strictly timeboxed with the kill criterion already stated ("kept only if it beats the baselines") enforced in practice, not just on paper. It's explicitly a bonus item; a rigorous baseline + statistical-model + evaluation story is a stronger, more finishable portfolio narrative than a mediocre, over-engineered ML model that consumed the time budget.
- **(C)** Everything else already excluded from MVP (dbt, Superset, hierarchical reconciliation, probabilistic/quantile forecasts, Slack/email delivery) stays excluded — no change needed there.

---

## 6. What happens next

This ADR finalizes Phase 00. Every decision (D1–D11) is now closed, including hardware sizing (§4.3: sufficient, work from `D:`). Consistent with the phase discipline in `CLAUDE.md` §18, **Phase 01 has still not started** — no data has been downloaded, no ingestion code has been written. The only remaining step is:

1. **Your explicit confirmation to proceed to Phase 01** with the scope in §2 — dataset acquisition, full-data profiling, the stratified item-selection query, and the dataset card, all run under `D:\...` on your machine — since starting a new phase is a deliberate step, not an automatic continuation.
