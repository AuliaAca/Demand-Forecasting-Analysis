# DemandFlow — Phase 00: Requirement Analysis & System Planning

**Status:** Planning only. No implementation code has been written and no dataset has been acquired.
**Source of truth:** the anonymized target-role profile in [`CLAUDE.md` §1](../CLAUDE.md), paraphrased from a real job description. The verbatim original and the target company's identity are kept privately, outside version control — see the notice at the top of `CLAUDE.md`.
**Date:** 2026-09-27

### Labels used in this document

| Label | Meaning |
|---|---|
| **[JD]** | Stated in the target-role profile. Wording here is paraphrased, not the verbatim source text; meaning is preserved. |
| **[DECISION]** | A DemandFlow implementation choice. It is not a practice of the target company. |
| **[ASSUMPTION]** | A simulation assumption, needed because no target-company data is used. |
| **[INFERENCE]** | Reasoning from the JD text, not stated in the JD. |
| **[VERIFY]** | Taken from public documentation or estimated. To be checked against the real data in Phase 01 or later. |

This document does not describe the target company's internal data, systems, forecasting logic, KPIs, supply-chain processes or operational practices, and does not name the target company. It contains none of these.

---

## 1. Job Requirement Decomposition

### 1.0 Company context (not a requirement)

The target JD's company-background text describes a quick-commerce company whose core value proposition is very fast delivery of groceries and everyday essentials. This is context, not a job requirement.

- **[INFERENCE]** The grocery and essentials domain is a reason to prefer a grocery-retail dataset.
- **[DECISION]** We do **not** derive technical requirements from the fast-delivery positioning (for example "hourly forecasting is required"). The JD does not state any.

### 1.1 About This Position: role objective

| ID | Exact JD wording | Capability it represents |
|---|---|---|
| RO-1 | "support the Demand Planning team in improving demand **forecast accuracy**" | Measuring forecast accuracy, finding where it is weak and improving it, as a service to a planning team |
| RO-2 | "…and **reliability**" | Forecasts that can be trusted consistently: stable bias, repeatable pipeline, trustworthy input data, known failure modes |
| RO-3 | "analyze **sales and demand patterns**" | Descriptive and diagnostic analysis of sales time series, and knowing when observed sales differ from true demand |
| RO-4 | "develop **forecasting logic**" | Designing forecasting methods, rules and features, beyond running a library call |
| RO-5 | "build **automated tools and monitoring**" | Automated, repeatable pipelines and outputs, plus ongoing accuracy monitoring |
| RO-6 | "to support **inventory and fulfillment decisions**" | Turning forecasts into outputs that support a decision, such as risk of under- or over-forecast |
| RO-7 | "ensuring customer demand is met **just-in-time**" | Knowing that forecast error causes stockouts (under-forecast) or excess stock (over-forecast) |
| RO-8 | "turning data into **practical forecasting solutions**" | Preferring usable, pragmatic solutions over complex ones that cannot be used |
| RO-9 | "working **cross-functionally** to improve **product availability**" | Collaboration, with product availability as the end outcome |

RO-8 and RO-9 come from the sentence "If you enjoy…". They are included because they state what the role is for.

### 1.2 Job Description: missions

| ID | Exact JD wording (sub-item preserved) | Capability it represents |
|---|---|---|
| M-1a | Analyze demand patterns across **SKUs** | Item-level behaviour: velocity, intermittency, lifecycle (launch and delisting), variability |
| M-1b | … across **hubs** | Location-level behaviour: differences between locations, network-level vs node-level patterns |
| M-1c | … across **categories** | Analysis along the product hierarchy: category seasonality and mix |
| M-1d | … across **campaigns** | Promotional and campaign effects: uplift, pull-forward, post-promotion dip |
| M-1e | … across **pricing** | How demand responds to price and to price changes |
| M-1f | … across **seasonal events** | Effects of holidays and events, and calendar-driven demand |
| M-2a | Improve forecasting logic by identifying **trends** | Trend detection and decomposition, and using trend in the forecast logic |
| M-2b | … **seasonality** | Weekly, monthly and annual seasonality, and seasonal baselines and features |
| M-2c | … **outliers** | Detecting outliers and deciding how to treat them in training data |
| M-2d | … **demand anomalies** | Detecting unusual demand periods and feeding that knowledge into the forecast logic |
| M-3a | **Monitor forecast accuracy** | Recurring accuracy measurement by segment and over time |
| M-3b | Turn findings into **actionable recommendations** | Recommendations that carry evidence, an action and an owner |
| M-4a | Build automated **datasets** | Curated, documented, reproducible analytical tables |
| M-4b | Build automated **dashboards** | Visual reporting for planners |
| M-4c | Build automated **trackers** | Tables and reports that track status over time (accuracy, open issues) |
| M-4d | Build automated **alerts** | Rule-based notifications when something needs attention |
| M-4 (purpose) | "…to make planning faster and smarter" | Automation that removes manual, repeated work |
| M-5a | Use **SQL** to transform data and automate repetitive processes | SQL transformation and validation |
| M-5b | Use **Python** … | Python for analysis, modelling and automation |
| M-5c | Use **BigQuery** … | A cloud data warehouse for transformation and serving |
| M-5d | … **automate repetitive processes** | Replacing manual steps with code |
| M-6a | Investigate **data issues** | Data quality checks, triage and handling |
| M-6b | Investigate **forecast discrepancies** | Finding and diagnosing unexpected forecast errors |
| M-6c | Perform **root-cause analysis** | A structured, evidence-based method for finding causes |
| M-6d | Work with relevant teams to resolve them | Routing each issue to the right owner and following it to resolution |
| M-7a | Partner with **Demand Planning** | Knowing what planners need from forecasts and analytics |
| M-7b | Partner with **Supply Chain** | Knowing how forecasts feed replenishment and availability |
| M-7c | Partner with **Data Engineering** | Data contracts, data quality ownership, pipeline handoff |
| M-7d | Partner with **Data Science** | Model evaluation, feature ideas, handing modelling issues over |
| M-7e | … to build **scalable solutions** | Designs that keep working as data, series count or users grow |

### 1.3 Requirements

#### 1.3.1 Candidate-level requirements (the project cannot replace these)

| ID | Exact JD wording | Why the project cannot replace it |
|---|---|---|
| R-1 | "**1–3 years of experience** in Data Analytics, BI, Supply Chain Analytics, Analytics Engineering, or a similar role." | Years of professional experience cannot be substituted with a portfolio project. |
| R-8a | "Comfortable working in a **fast-paced environment**" | Describes behaviour in a real workplace. |
| R-8b | "…and **collaborating across teams**" | Real collaboration needs real teams. The project can only show artifacts that are ready to hand over. |

#### 1.3.2 Skills the project can demonstrate, fully or partly

| ID | Exact JD wording | Capability | How far the project can show it |
|---|---|---|---|
| R-2a | "Strong **SQL**" | SQL transformation, window functions, modelling, validation | Demonstrable |
| R-2b | "experience working with **large datasets**" | Processing tens to hundreds of millions of rows efficiently | Skill is demonstrable. "Experience" in a professional sense is not. |
| R-2c | "**BigQuery is a plus**" | Cloud data warehouse usage | Demonstrable. The JD calls it a **plus**, not a mandatory requirement. |
| R-3 | "Comfortable using **Python** for analysis and automation" | Python analysis, modelling, scripting, automation | Demonstrable |
| R-4a–e | "Understanding of **forecasting**, **seasonality**, **trends**, **outliers**, and **forecast accuracy**" | Forecasting concepts and evaluation | Demonstrable |
| R-5 | "Experience with **dashboards, reporting automation, data products, or monitoring tools**" | Building consumable analytical outputs | The capability is demonstrable. The professional "experience" is not. |
| R-6 | "Strong **analytical and problem-solving** skills with great **attention to detail**" | Rigour: validation, reconciliation, documented decisions | Partly, through the quality of the work |
| R-7 | "Able to turn complex analysis into **clear business insights and recommendations**" | Communication aimed at decision makers | Partly, through written findings and recommendations |

### 1.4 Bonus points

| ID | Exact JD wording | Capability | How far the project can show it |
|---|---|---|---|
| B-1 | "Experience in **e-commerce, quick commerce, retail, FMCG, or supply chain**" | Domain experience | The project gives **retail/grocery domain exposure** only. That is not industry experience. |
| B-2a | "exposure to **Airflow**" | Workflow orchestration | Project work can count as exposure |
| B-2b | "…**GCP**" | Google Cloud usage | Exposure, via BigQuery |
| B-2c | "…**Looker Studio**" | BI dashboarding | Exposure |
| B-2d | "…**Superset**" | BI dashboarding (open source) | Exposure if chosen. Not planned by default (§7). |
| B-2e | "…**Git**" | Version control | Exposure, used throughout |
| B-2f | "…**machine-learning forecasting**" | ML-based forecasting | Exposure, if backtests justify it |

**[INFERENCE]** The bonus says "**exposure to**" for the tools and "**experience in**" for the industries. Project work is honest evidence of exposure. It is not industry experience.

---

## 2. Requirement → Project Mapping

Mapping format: **JD requirement → capability → proposed DemandFlow evidence → limitation or assumption.**
"Favorita" means the dataset recommended in §5. That choice still needs your approval (§14, D1).

### 2.1 Role objective

| ID | JD requirement | Capability | Proposed DemandFlow evidence | Limitation / assumption |
|---|---|---|---|---|
| RO-1 | Improving forecast accuracy | Measure and improve accuracy | Backtested accuracy of the baselines vs improved models, broken down by segment and horizon (Phases 05–08) | Improvement is measured against our own baselines. There is no benchmark from the target company. |
| RO-2 | Forecast reliability | Consistent, trustworthy forecasts | Bias tracking, error stability across forecast origins, data-quality gates before forecasting, tested pipeline (Phases 02, 08, 10, 15) | Reliability is shown on a historical replay, not in live operation |
| RO-3 | Analyze sales and demand patterns | Pattern analysis | EDA notebook plus SQL analysis marts (Phase 04) | The dataset records **sales**, not demand. Demand during stockouts is not observed, so the data is censored. |
| RO-4 | Develop forecasting logic | Method design | Documented logic that moves from baselines to statistical models to ML, with each feature justified by an EDA finding (Phases 05–07) | The method is our choice. The JD does not prescribe one. |
| RO-5 | Automated tools and monitoring | Automation and monitoring | A pipeline run by a single `as-of date` parameter, monitoring tables, alerts (Phases 10–12) | Runs on historical replay |
| RO-6 | Support inventory and fulfillment decisions | Output that supports decisions | Over- and under-forecast risk flags per hub × SKU, with a perishables view | **Favorita has no inventory, stock or order data**, so fill rate and stock cover cannot be computed. [ASSUMPTION] Under-forecast is used as a proxy for stockout risk and over-forecast as a proxy for waste risk. |
| RO-7 | Demand met just-in-time | Relating error to timing | Daily forecasts over a short horizon, evaluated per horizon day (see §4) | No lead times or stock levels are available. Just-in-time is framed, not measured. |
| RO-8 | Practical forecasting solutions | Pragmatism | Every model must beat a simple baseline in the backtest to be kept. A runbook documents how to operate the pipeline. | — |
| RO-9 | Improve product availability | Availability outcome | Written limitation, plus an optional availability module (§9) | **Limited by dataset.** Favorita has no stockout labels, and a missing sale row can mean zero demand *or* no stock. |

### 2.2 Missions

| ID | JD requirement | Capability | Proposed DemandFlow evidence | Limitation / assumption |
|---|---|---|---|---|
| M-1a | SKUs | Item-level analysis | SKU velocity and intermittency classes (for example ABC and ADI/CV²), lifecycle flags, top-N contribution | ~4,100 items [VERIFY] |
| M-1b | Hubs | Location-level analysis | Store-level demand profiles, store type and cluster comparison, store traffic from the transactions file | [ASSUMPTION] Favorita stores are **supermarkets used as stand-ins for hubs**. They are not quick-commerce hubs or dark stores. |
| M-1c | Categories | Hierarchy analysis | Family, class and perishable-flag analysis | Categories follow Favorita's own taxonomy |
| M-1d | Campaigns | Promotion effect analysis | Promotion uplift from the `onpromotion` flag, plus retail events listed in the holiday/events file (for example Black Friday) [VERIFY] | **Partial.** The flag marks an item on promotion in a store on a day. It is not a named campaign with mechanics or budget. About 16% of `onpromotion` values are NaN. |
| M-1e | Pricing | Price-demand analysis | None in the primary dataset. Optional secondary module (§9). | **Limited by dataset.** Favorita has **no item price**. The oil price file is a macroeconomic indicator and **must not be presented as pricing**. |
| M-1f | Seasonal events | Calendar effects | National, regional and local holidays (including transferred and bridge days), paydays, and a documented earthquake period | The calendar is **Ecuadorian**, so it does not represent the target company's actual regional seasonal calendar |
| M-2a | Trends | Trend identification | STL decomposition, rolling trend statistics, trend features | — |
| M-2b | Seasonality | Seasonality identification | Day-of-week, payday, monthly and annual profiles, and a seasonal-naive baseline | Only ~4.6 years of history, so annual seasonality is estimated from 4 cycles |
| M-2c | Outliers | Outlier handling | Robust detection on residuals (MAD or IQR), and a written treatment policy: flag and cap for training, **never delete** | — |
| M-2d | Demand anomalies | Anomaly detection | An anomaly-flag table at network, store and category level, validated against a documented disruption (the April 2016 earthquake) [VERIFY] | — |
| M-3a | Monitor forecast accuracy | Monitoring | Accuracy tracker: WAPE, bias, MAE and RMSE by as-of week × segment × horizon | — |
| M-3b | Actionable recommendations | Recommendation writing | A recommendations log. Each entry records finding, evidence, action, owner role and status. | Owner roles are fictional (§4) |
| M-4a | Datasets | Curated tables | Layered SQL models with a documented grain for every table (staging, then intermediate, then marts) | — |
| M-4b | Dashboards | Dashboarding | Looker Studio dashboard on BigQuery marts. A local generated report is the MVP fallback. | — |
| M-4c | Trackers | Status tracking | Accuracy tracker, plus a discrepancy/investigation tracker with a status workflow | — |
| M-4d | Alerts | Alerting | Rule-based alerts with thresholds held in config (accuracy decline, bias drift, data-quality failure, anomaly), an alert log and a generated digest | Delivered to a file or report by default. Slack or email is optional. |
| M-5a | SQL | SQL transformation | SQL files for staging, intermediate and marts; data-quality assertions; accuracy aggregation; RCA drill-down queries | — |
| M-5b | Python | Python analysis and automation | Python package for ingestion, forecasting, evaluation, alerts and the CLI | — |
| M-5c | BigQuery | Cloud warehouse | Marts loaded to BigQuery with partitioning and clustering. Bytes processed and cost are logged. (Phase 13) | The JD lists BigQuery as "a **plus**" in Requirements. Free-tier limits apply (§8). |
| M-5d | Automate repetitive processes | Automation | One CLI command per as-of run. Nothing in the production path requires a manual notebook step. | — |
| M-6a | Data issues | Data quality | A data-quality rule catalog recording rule, finding, severity, consequence and handling (CLAUDE.md §12). Checks run as pipeline gates. | — |
| M-6b | Forecast discrepancies | Discrepancy detection | Discrepancy rules at segment level (for example a hub × family × week bias or WAPE beyond a threshold) | Thresholds come from the backtest distribution, not from any KPI of the target company |
| M-6c | Root-cause analysis | RCA | An RCA workflow using a drill-down tree and error-contribution decomposition, plus written case studies that use evidence language (CLAUDE.md §13) | Findings are stated as correlation, never as proven causation |
| M-6d | Work with relevant teams to resolve | Handoff | Each finding is routed to the stakeholder role that would own the fix, with a resolution status in the tracker | **Real collaboration is not reproducible.** Roles are simulated. |
| M-7a | Demand Planning | Stakeholder need | A use-case document: forecasts, accuracy by segment, explanations | Simulated perspective |
| M-7b | Supply Chain | Stakeholder need | A use-case document: under- and over-forecast risk flags, perishables view | Simulated perspective |
| M-7c | Data Engineering | Stakeholder need | Data contracts (grain, keys, freshness) and data-quality tickets | Simulated perspective |
| M-7d | Data Science | Stakeholder need | An evaluation framework and model-issue findings | Simulated perspective |
| M-7e | Scalable solutions | Scalability | The full ~125M-row history is processed with columnar engines. The design uses as-of runs, incremental processing, one global model instead of one model per series, and BigQuery partitioning and clustering. Runtime, memory and bytes scanned are recorded. | Scale here means a large public dataset. It does not mean enterprise infrastructure (CLAUDE.md §3.8). |

### 2.3 Requirements and bonus

| ID | JD requirement | Capability | Proposed DemandFlow evidence | Limitation / assumption |
|---|---|---|---|---|
| R-1 | 1–3 years experience | Professional tenure | **None. Not project-replaceable.** | The README will say so explicitly |
| R-2a/b | Strong SQL, large datasets | SQL at scale | SQL layer over ~125M rows [VERIFY], with row-count and sum reconciliation checks | Skill, not professional experience |
| R-2c | BigQuery is a plus | BigQuery | Phase 13 BigQuery port | Called a plus, not mandatory |
| R-3 | Python | Python | The package, its tests and the CLI | — |
| R-4a–e | Forecasting concepts | Forecasting | Phases 04–08 | — |
| R-5 | Dashboards, reporting automation, data products, monitoring tools | Analytical products | Dashboard, generated reports, tracker and alerts | Capability, not professional experience |
| R-6 | Analytical skill, attention to detail | Rigour | Data-quality catalog, reconciliation checks, decision log, tests | Only partly demonstrable. A reviewer judges it. |
| R-7 | Clear business insights and recommendations | Communication | A findings summary for each phase, RCA memos and the recommendations log | Only partly demonstrable |
| R-8a/b | Fast-paced environment, cross-team collaboration | Workplace behaviour | Artifacts ready to hand over: data contracts, documentation, commits made through PRs | **Not project-replaceable** |
| B-1 | Retail and related industry experience | Domain | Grocery-retail data | Exposure, not experience. Favorita is supermarket retail, not quick commerce. |
| B-2a | Airflow | Orchestration | A local Airflow DAG with a backfill of the historical replay (optional, Phase 12) | Run locally only. Managed Airflow is excluded because of cost. |
| B-2b | GCP | Cloud | BigQuery, with Looker Studio on top | — |
| B-2c | Looker Studio | Dashboard | Phase 14 | — |
| B-2d | Superset | Dashboard | Not planned by default | Building a second dashboard adds no new evidence |
| B-2e | Git | Version control | The whole project, with meaningful commits, branches and CI | — |
| B-2f | ML forecasting | ML | A LightGBM global model (Phase 07). It is kept only if it beats the baselines. | May be rejected on evidence, which is also a valid result |

---

## 3. Project Concept

**DemandFlow** is a reproducible, local-first analytics system. It simulates the loop that a demand-planning analytics function would run for a grocery retailer with many locations:

> ingest → validate → model → analyze demand → forecast → evaluate → monitor → alert → investigate → recommend

### JD problems it simulates

| JD problem | Question DemandFlow answers | JD items |
|---|---|---|
| Understanding demand | Where and why does demand differ across SKUs, hubs, categories, promotions and events? | M-1, RO-3 |
| Forecasting logic | Which logic handles the trends, seasonality, outliers and anomalies we found? | M-2, RO-4 |
| Accuracy | How accurate is the forecast, and where is it getting worse? | M-3, RO-1, RO-2 |
| Automation | How does a planner find out without doing manual work? | M-4, M-5, RO-5 |
| Investigation | When a number looks wrong, is it the data or the forecast, and why? | M-6 |
| Handoff and scale | Can the solution scale, and can other teams take it over? | M-7 |

### Core design idea: historical replay [DECISION]

The data is static and historical, so DemandFlow **simulates operation over time**:

1. Choose a sequence of as-of dates, for example weekly over several months of history.
2. Each run sees only data up to and including its as-of date. It forecasts the next *H* days and stores them with `as_of_date` and `horizon`.
3. Later runs treat the actuals for those days as having "arrived". They evaluate the stored forecasts and update the accuracy tracker.
4. Monitoring rules fire alerts. Alerts open discrepancy-tracker entries, and these drive the RCA work.

Replay does two jobs. It turns a static Kaggle dataset into a realistic stream for monitoring and alerting. It also enforces time-aware validation with no leakage (CLAUDE.md §10). If the replay window covers a documented disruption, such as the April 2016 earthquake [VERIFY], we can check whether the alerts fire where they should.

### What DemandFlow is not

- It is not the target company's system, not a replica of it, and not built from the target company's data.
- It is not a live production system.
- It does not involve real stakeholders.
- It is not an inventory optimisation or ordering engine.

---

## 4. Business Scenario

Every item in this scenario is a **[ASSUMPTION]** made so that the JD requirements can be tested. None of it describes the target company.

| # | Scenario element | Assumption | Why it is needed |
|---|---|---|---|
| S1 | The business | A fictional grocery retailer with many locations, called **"the Retailer"**. Its data comes from the chosen public dataset. | We need a setting that is not the target company |
| S2 | Hubs | Each store in the dataset is treated as a **hub**, meaning a fulfillment location | M-1b uses the word "hubs" |
| S3 | Planning unit | **hub × SKU × day** | This is the grain of the recommended dataset |
| S4 | Forecast cadence | One forecast run per week, with the as-of date on a Sunday | Gives regular monitoring intervals |
| S5 | Horizon | Daily forecasts for the next **14 days** (horizon 1–14) | Short horizon, consistent with a replenishment use case. It is close to the original Kaggle test window of 16 days [VERIFY]. |
| S6 | Promotions known in advance | Promotion flags for the forecast window are known at forecast time, as planned promotions | Mirrors the Kaggle setup, where `onpromotion` was supplied for the test period [VERIFY]. If you reject this assumption, promotion features must be lagged. |
| S7 | Calendar known in advance | Holidays and events are known at forecast time | Holidays are scheduled |
| S8 | Stakeholder roles (fictional) | **Demand Planner**: uses forecasts and accuracy by segment. **Supply Chain / Replenishment**: uses under- and over-forecast risk flags. **Data Engineering**: owns the source data and receives data-issue tickets. **Data Science**: owns modelling methods and receives model-issue findings. | Mirrors the team names in the JD. They are perspectives, not real collaboration. |
| S9 | Decision supported | Replenishment. DemandFlow supplies forecasts and risk signals but does **not** compute order quantities. | No stock or lead-time data is available |
| S10 | Cost of error framing | Under-forecast is used as a proxy for lost sales (stockout risk). Over-forecast is used as a proxy for excess stock, with extra weight for **perishables**. | Links forecast error to RO-6 and RO-7 without inventory data |
| S11 | Success criteria (project, not the target company's KPIs) | Lower WAPE and lower absolute bias than the seasonal-naive baseline in the backtest. Alerts fire on known historical disruptions during replay. Every discrepancy is traced to evidence. | Needed to judge the project |
| S12 | Alert thresholds | Taken from the backtest error distribution, for example "WAPE worse than the segment's trailing median by more than X percentage points" | Avoids inventing KPIs |

---

## 5. Dataset Options

The facts below come from public documentation and community write-ups. They are **[VERIFY]** until Phase 01 checks them against the files. Nothing has been downloaded.

### 5.1 Candidates

**A. Corporación Favorita Grocery Sales Forecasting** (Kaggle, 2017). Grocery chain in Ecuador.
- `train`: ~125.5M rows of `date, store_nbr, item_nbr, unit_sales, onpromotion`, daily from 2013-01-01 to 2017-08-15.
- `stores`: 54 stores with city, state, type and cluster.
- `items`: ~4,100 items with family, class and a `perishable` flag.
- `transactions`: transactions per store per day.
- `holidays_events`: type, locale (national, regional or local), locale name and a transferred flag.
- `oil`: daily oil price.
- Documented quirks:
  - Rows with zero sales are **not included**, and there is no stock information.
  - About 16% of `onpromotion` values are NaN.
  - Negative `unit_sales` means returns.
  - Units can be fractional (items sold by weight).
  - Sales were abnormal in the weeks after the 2016-04-16 earthquake.
  - Public-sector wages are paid on the 15th and on the last day of the month.
  - No rows are reported for 25 December.

**B. Store Sales – Time Series Forecasting** (Kaggle Playground, derived from Favorita).
- Store × product family per day: 54 × 33, same period, ~3.0M rows.
- `onpromotion` is a count of promoted items.
- Includes the same holidays, oil and transactions files.

**C. M5 Forecasting – Accuracy** (Kaggle 2020, Walmart).
- 3,049 items, 10 stores in 3 US states, 3 categories, 7 departments.
- 1,941 days from 2011-01-29, which is ~59M rows in long format (30,490 series × 1,941 days).
- `calendar`: named events with a type, plus SNAP days for each state.
- `sell_prices`: weekly price per store × item.
- There is no promotion flag. Promotions can only be inferred from price drops, which is an inference and not ground truth.
- Zeros are included, and many series are intermittent. There are leading zeros before an item launches.

**D. FreshRetailNet-50K** (Dingdong, 2025, Hugging Face).
- 50,000 store × product series across 898 stores in 18 Chinese cities, covering 863 perishable SKUs.
- About 90 days, reported as March to June 2024.
- **Hourly** sales with **hourly stockout status**.
- Discount, holiday and activity flags, weather data, and a 3-level category hierarchy.

**E. dunnhumby "Breakfast at the Frat"**.
- 79 stores, 156 weeks, about 58 products in 4 categories: mouthwash, pretzels, frozen pizza and boxed cereal.
- Units, visits and spend.
- Base price and shelf price, plus feature, display and temporary-price-reduction (TPR) flags.

**F. Rossmann Store Sales** (Kaggle 2015).
- 1,115 drugstores, daily **store-level** sales, ~1.0M rows.
- Promotion, state holiday and school holiday flags.

**Excluded after a quick screen:**
- Instacart: no calendar dates.
- UCI Online Retail II: no hubs, no promotions, and it is UK e-commerce transaction data.
- Kaggle "Store Item Demand": synthetic, with no metadata.
- BigQuery public `thelook_ecommerce`: synthetic.
- BigQuery public Iowa Liquor Sales: records retailers' wholesale purchases from the state, not consumer demand [VERIFY].

### 5.2 Comparison against the JD dimensions

Legend: ✔ available · ◐ partial or proxy · ✗ not available

| JD dimension | A. Favorita | B. Store Sales | C. M5 | D. FreshRetailNet-50K | E. Breakfast at the Frat | F. Rossmann |
|---|---|---|---|---|---|---|
| SKU / product (M-1a) | ✔ ~4,100 items | ✗ family only | ✔ 3,049 | ✔ 863 | ◐ ~58 | ✗ |
| Hub / store (M-1b) | ✔ 54 stores with city, state, type, cluster | ✔ 54 | ◐ 10 stores | ✔ 898 stores, 18 cities | ✔ 79 | ✔ 1,115 |
| Category (M-1c) | ✔ family, class, perishable | ✔ family | ◐ 3 categories, 7 departments | ✔ 3 levels | ◐ 4 | ✗ |
| Campaign / promotion (M-1d) | ◐ promotion flag per item × store × day, plus retail events | ◐ promoted-item count | ✗ inferred from price drops only | ◐ activity flag | ✔ feature, display, TPR | ◐ store-level promotion |
| Pricing (M-1e) | ✗ | ✗ | ✔ weekly price | ✔ discount | ✔ base and shelf price | ✗ |
| Seasonal / calendar (M-1f) | ✔ national, regional and local holidays; paydays; events | ✔ | ✔ events and SNAP | ◐ holiday flag over only ~3 months | ◐ week index only | ◐ holiday flags |
| Time-series length | ✔ ~4.6 years daily | ✔ | ✔ ~5.3 years daily | ✗ ~90 days hourly | ◐ 3 years weekly | ◐ ~2.6 years daily |
| Scale | ✔ ~125M rows | ◐ ~3M | ✔ ~59M (long format) | ✔ ~4.5M series-days (×24 hours) | ✗ ~0.5M | ◐ ~1M |
| Availability / stockouts (RO-9) | ✗ | ✗ | ✗ | ✔ hourly labels | ✗ | ◐ store open flag |
| Real data issues to investigate (M-6a) | ✔ rich (see A above) | ◐ | ◐ | ◐ | ◐ | ◐ |
| Closeness to grocery / quick commerce | ✔ grocery | ✔ grocery | ◐ general merchandise | ✔ fresh grocery e-commerce | ◐ consumer packaged goods | ✗ drugstore |

### 5.3 What each dataset can and cannot demonstrate

| Dataset | Can demonstrate | Cannot demonstrate |
|---|---|---|
| A. Favorita | SKUs, hubs (as a proxy), categories, promotions (partial campaigns), a rich seasonal and event calendar, multi-year trend and seasonality, large-scale SQL, genuine data issues for M-6 | **Pricing.** Stockouts and availability. Named campaigns. The target company's actual regional calendar. |
| B. Store Sales | Hubs, categories, calendar; quick to work with | **SKUs**, pricing, availability, large scale |
| C. M5 | SKUs, pricing, calendar and events, multi-year patterns, large scale | **Campaigns/promotions** (only as an inference). Hub network breadth (10 stores). Fine-grained categories. |
| D. FreshRetailNet-50K | SKUs, hubs, categories, pricing (discount), campaigns (activity flag), **availability and censored demand**, hourly patterns | **Annual seasonality, multi-year trend, most seasonal events** (the window is only ~90 days) |
| E. Breakfast at the Frat | Pricing and promotion mechanics in depth | SKU breadth, daily grain, seasonal events, large scale |
| F. Rossmann | Hubs, store-level promotions, holidays | SKUs, categories, pricing |

### 5.4 Recommendation (needs your approval, D1)

**Primary dataset: A. Corporación Favorita** [DECISION pending].

- **Why:**
  - It covers 4 of the 6 M-1 dimensions strongly and campaigns partly.
  - It is grocery data, which is the closest domain to the JD's company context.
  - It has the broadest hub-like network with a long daily history, which supports M-2a and M-2b.
  - Its real, documented data issues suit M-6 better than any other candidate: omitted zeros, promotion NaNs, returns, closures, the earthquake shock and missing Christmas days.
  - At ~125M rows it genuinely tests R-2 and M-7e.
- **Main gap:** there is no pricing at all (M-1e). This will be recorded as **Limited by dataset**. It will not be approximated with oil prices.
- **Runner-up: C. M5.** Choose it instead if showing **pricing** matters more to you than campaigns and hub count.
- **Optional supplements** (Advanced scope only, §9):
  - A small pricing/promotion module using M5 `sell_prices` or Breakfast at the Frat.
  - An availability/censored-demand module using FreshRetailNet-50K.
  - Neither is part of the MVP.

---

## 6. Proposed Architecture

This is a project design. Nothing in it describes the target company's architecture. It is the **minimum** needed to produce evidence for the JD items in §2.

```
                 demandflow run --as-of YYYY-MM-DD      (Python CLI; the optional Airflow DAG calls the same tasks)
                                   │
  Public dataset files ──► ingest (Python) ──► raw Parquet (immutable copy)
                                   │
                                   ▼
                     Data-quality checks (SQL + Python) ──► DQ results table ──► gate (stop / warn)
                                   │
                                   ▼
                SQL transformations (DuckDB): staging ──► intermediate ──► marts
                                   │
        ┌──────────────────────────┼─────────────────────────────┬──────────────────────────┐
        ▼                          ▼                             ▼                          ▼
   EDA (Phase 04)        Forecasting (Python)            Anomaly detection         Calendar / promo features
                         baselines → stat → ML
                                   │
                                   ▼
                  fct_forecast (as_of_date, horizon, hub, SKU, target_date, model, forecast)
                                   │   + actuals as they "arrive" in replay
                                   ▼
                 Evaluation & monitoring marts (SQL): accuracy tracker by as_of × segment × horizon
                                   │
                                   ▼
              Alert rules (config) ──► alert log ──► discrepancy/investigation tracker
                                   │
                                   ▼
              RCA workflow (SQL drill-downs + error-contribution decomposition) ──► RCA memos
                                   │
                                   ▼
                          Recommendations log ──► generated planning report
                                   │
                                   ▼
          Publish marts ──► BigQuery (partitioned / clustered) ──► Looker Studio dashboard
```

### 6.1 Where each capability fits

| Capability | Where it sits | Technology |
|---|---|---|
| **Datasets** (M-4a) | Raw → staging → intermediate → marts, with a documented grain and keys for each table | Parquet, DuckDB SQL, and a BigQuery copy of the marts |
| **SQL** (M-5a) | Typing and renaming in staging, data-quality assertions, all transformations, accuracy aggregation, RCA drill-downs | DuckDB SQL, ported to BigQuery SQL in Phase 13 |
| **Python** (M-5b) | Download and ingestion, CLI and run orchestration, forecasting, metrics, alert rule engine, report generation | Python package `demandflow` |
| **BigQuery** (M-5c) | Serving layer for the marts and monitoring tables that the dashboard reads. Shows partitioning, clustering and cost control. | BigQuery (sandbox or free tier) |
| **Forecasting** (M-2, RO-4) | Reads the dense modelling table and writes `fct_forecast` with `as_of_date` and `horizon` | Python: baselines, then statistical models, then LightGBM |
| **Monitoring** (M-3a) | SQL marts: accuracy by as-of week × segment × horizon, and bias drift | SQL |
| **Alerts** (M-4d) | Python rule engine over the monitoring and DQ tables. Writes `fct_alert` and a Markdown alert digest. | Python, with thresholds in YAML config |
| **Trackers** (M-4c) | (1) Accuracy tracker (a mart). (2) Discrepancy/investigation tracker: one row per issue with status (open, investigating, resolved), owner role, evidence link and resolution. | SQL table, Python writer |
| **Dashboards** (M-4b) | Looker Studio on the BigQuery marts. The MVP fallback is a generated static report. | Looker Studio |
| **RCA** (M-6c) | Reusable SQL drill-down templates. A Python helper that splits total absolute error by dimension. Written case notes. | SQL, Python, Markdown |

### 6.2 Planned data layers and grain [DECISION]

| Layer | Examples | Grain / rule |
|---|---|---|
| raw | `raw_train`, `raw_stores`, `raw_items`, `raw_holidays_events`, `raw_transactions`, `raw_oil` | Exactly as delivered, converted to Parquet with no changes |
| staging | `stg_sales`, `stg_items`, … | One row per source record, typed. Data-quality flags are **added**. No rows are deleted. |
| intermediate | `int_calendar_by_store` (holidays resolved per store locale, transferred days handled, paydays); `int_sales_daily_dense` (hub × SKU × day **within the modelling scope**, with missing rows zero-filled and marked by `is_imputed_zero`) | The zero-fill assumption is documented |
| marts | `dim_hub`, `dim_sku`, `dim_date`, `fct_sales_daily`, `fct_forecast`, `fct_forecast_accuracy`, `fct_dq_result`, `fct_alert`, `trk_investigation`, `trk_recommendation` | Each table has a written data contract |

Storing forecasts with `as_of_date` and `horizon` is the key design choice. It lets us monitor how accuracy changes over time and with horizon, which M-3a requires. Without it we would only have a single backtest score.

---

## 7. Technology Decisions

Status column: **Mandatory** means SQL or Python is explicitly required by the JD. **JD plus** means BigQuery, which the Requirements call "a plus". **Bonus** means it is listed in the JD bonus points. **Project** means our own choice, not in the JD.

| Technology | Role in DemandFlow | How it helps show the JD | Status | Local / free alternative | Trade-off |
|---|---|---|---|---|---|
| **Python 3.11+** | Ingestion, forecasting, evaluation, alerts, CLI | M-5b, R-3 | Mandatory | — | — |
| **SQL** | Transformations, data-quality checks, marts, monitoring, RCA | M-5a, R-2a | Mandatory | — | — |
| **DuckDB** | Local SQL engine and single-file warehouse | Makes it possible to run SQL over ~125M rows locally at $0 (R-2b, M-7e) | Project | PostgreSQL is slower for analytics and needs setup. SQLite is too slow at this size. pandas alone runs out of memory. | Its SQL dialect differs from BigQuery's, so Phase 13 needs porting. That porting is also a learning outcome. |
| **Parquet** | Columnar file storage | Efficient processing at scale | Project | CSV | Needs a conversion step |
| **pandas** (Polars optional) | Dataframe work on data inside the modelling scope | R-3 | Project | — | pandas is familiar and common in interviews. Heavy aggregation goes to DuckDB instead. |
| **statsforecast / statsmodels** | Statistical models: ETS, STL, Croston/TSB for intermittent series | R-4, M-2 | Project | — | statsforecast is fast across many series. statsmodels is easier to explain. Choice made in Phase 06. |
| **LightGBM + scikit-learn** | ML global forecasting model | B-2f | Bonus | — | Harder to explain, and features can leak the future. Kept only if it beats the baselines. |
| **BigQuery** | Cloud warehouse for marts; dashboard source | M-5c, R-2c, B-2b | JD plus | DuckDB only (Phase 13 would then be reduced) | Account setup, sandbox limits, dialect differences |
| **Looker Studio** | Dashboard | M-4b, B-2c | Bonus | Superset (self-hosted in Docker); a generated local report | Free and shareable, and connects natively to BigQuery. Not version-controlled, so we keep a written spec and screenshots in Git. |
| **Superset** | — | B-2d | Bonus, **not chosen by default** | — | A second dashboard adds no new evidence. Used only if Looker Studio is rejected. |
| **Airflow** | Orchestrates the as-of runs; backfills the historical replay | B-2a, M-5d | Bonus, optional | CLI plus a Makefile | Docker overhead. Runs locally only; managed Airflow is excluded because of cost (§8). |
| **Git + GitHub** | Version control, PR workflow | B-2e | Bonus | — | — |
| **GitHub Actions** | CI: lint and tests on small fixtures | RO-2, R-6 | Project | Local pytest only | CI cannot use the full dataset, so tests run on fixtures |
| **pytest + ruff** | Testing and linting | Engineering principles in CLAUDE.md §14 | Project | — | — |
| **YAML config** | Scope, horizons, alert thresholds | M-4d | Project | Hard-coded constants | — |
| **dbt** | **Not planned by default** (D6) | Would add tests, lineage and docs | Not in JD | Plain layered SQL with a small runner | One more tool to learn; keeps the focus on SQL itself |
| **Great Expectations / Pandera** | **Not planned** | — | Not in JD | SQL assertion checks | Custom checks are lighter and easier to see into |

---

## 8. Cost Analysis

| Component | Local / free | Free tier | Cloud / paid | Recommendation |
|---|---|---|---|---|
| Storage and SQL | DuckDB + Parquet: **$0** | **BigQuery sandbox**: 10 GiB storage, 1 TiB of queries per month, tables expire after 60 days, no DML, no credit card needed [per Google documentation; VERIFY] | BigQuery on-demand pricing beyond the free tier [VERIFY current price per TiB] | Local as primary. BigQuery for marts only. |
| Orchestration | Airflow in Docker locally: **$0** | — | Google-managed Airflow (Cloud Composer). Public sources report roughly **$300–400+ per month** for a small environment even when idle [VERIFY]. | **Local only. Never managed Airflow.** It adds cost and no extra evidence. |
| Dashboard | Superset in Docker, or a local report: $0 | **Looker Studio: $0** | Looker Studio Pro (not needed) | Looker Studio free |
| CI | Local pytest | GitHub Actions (free for public repositories) | — | GitHub Actions |
| ML compute | Laptop | Google Colab free tier (optional) | Vertex AI | Laptop, with models scoped to fit it |
| Alert delivery | File or Markdown digest | Slack incoming webhook or email (optional) | Cloud Functions | File by default |

### BigQuery sizing estimate [VERIFY]

- The sales fact table is ~125.5M rows at ~33 logical bytes per row (DATE, 2 × INT64, FLOAT64, BOOL). That is about **4.1 GB**.
- It fits in the 10 GiB sandbox but uses ~40% of it. Every full scan reads ~4 GB, which allows about 250 full scans per TiB per month.
- **Mitigations:**
  - Partition by date and cluster by hub and SKU.
  - Point the dashboard at aggregated marts, not the raw fact table.
  - Set `maximum_bytes_billed` on every job.
  - Log a dry-run estimate before each query.

These controls also serve as evidence of cost awareness.

### Sandbox trade-off

Sandbox tables expire after 60 days. A Looker Studio dashboard built on them therefore **breaks after 60 days** unless the data is reloaded. For a portfolio link that stays up, pick one:

- **(a)** Enable billing, with a very low budget alert and query quotas. Expected cost stays $0 within the free tier.
- **(b)** Run a scripted reload.
- **(c)** Accept that the dashboard is temporary and keep screenshots.

This is decision D7.

**Expected total project cost is $0** if these recommendations are followed.

---

## 9. Project Scope

Scope follows JD coverage. Adding technologies is not a goal in itself. Phases run in the order in CLAUDE.md §17. Scope decides which phases are full, reduced or optional (CLAUDE.md §18).

### MVP: the core JD evidence

| Component | JD items |
|---|---|
| Phase 01: reproducible acquisition and a dataset card with verified JD-dimension coverage | M-4a, M-1 (coverage) |
| Phase 02: data-quality rule catalog and report | M-6a, R-6 |
| Phase 03: layered SQL models in DuckDB with documented grain and reconciliation | M-5a, R-2, M-4a |
| Phase 04: EDA across every available JD dimension | M-1a–f, M-2a–d, RO-3 |
| Phase 05: naive, seasonal-naive and moving-average baselines with a rolling-origin backtest | M-2, R-4, RO-4 |
| Phase 08: evaluation framework (WAPE, bias, MAE, RMSE) by segment and horizon | M-3a, RO-1, RO-2 |
| Phase 09: at least one end-to-end RCA case study, plus the recommendations log | M-6b–d, M-3b, R-7 |
| Phases 10–11: accuracy tracker, rule-based alerts, discrepancy tracker, and a generated planning report | M-3a, M-4c, M-4d, RO-5 |
| Throughout: Git, tests for metrics and data-quality logic | B-2e, R-6 |

### Intermediate

| Component | JD items |
|---|---|
| Phase 06: statistical models (ETS, STL, intermittent-demand methods) | R-4 |
| Phase 07: LightGBM global model with promotion, holiday and calendar features. Kept only if the backtest justifies it. | B-2f |
| Phase 13: BigQuery marts with partitioning, clustering and cost logging | M-5c, R-2c, B-2b, M-7e |
| Phase 14: Looker Studio dashboard | M-4b, R-5, B-2c |
| Phase 15: testing and reliability (CI, idempotent runs, end-to-end smoke test on fixtures) | RO-2, R-6 |

### Advanced / optional

| Component | Why it is optional |
|---|---|
| Phase 12: local Airflow DAG with a backfill of the replay | Airflow is only a **bonus** item. A CLI plus Makefile can cover M-5d without it. |
| Pricing module on a secondary dataset (M5 or Breakfast at the Frat) | Fills the M-1e gap, at the cost of a second data pipeline |
| Availability/censored-demand module on FreshRetailNet-50K | Evidence for RO-9 and RO-7, but a different grain and a short history |
| Probabilistic (quantile) forecasts and service-level framing | Goes beyond the explicit JD items |
| Hierarchical reconciliation (SKU, family, hub) | Useful, but not named in the JD |
| Slack or email alert delivery | The alert logic is the evidence. Delivery is plumbing. |
| Superset | Only if Looker Studio is rejected |

**Out of scope:** inventory optimisation and order quantities, real-time streaming, managed Airflow, Vertex AI, deep-learning forecasting (unless strongly justified), and synthetic data fabricated to resemble the target company's own operations.

---

## 10. Learning Roadmap

| Phase | What you learn | JD capability demonstrated | Evidence at the end of the phase |
|---|---|---|---|
| 00 Planning | Breaking down a JD, traceability, scoping | All items (planning), R-7 | This document |
| 01 Dataset | Data sourcing, licence terms, reproducible acquisition, profiling, dataset cards | M-4a, M-5b; M-1 coverage checked on the real data | Download script, checksums, raw Parquet, dataset card |
| 02 Data Quality | Data-quality dimensions, rule design, severity levels, handling decisions | M-6a, R-6 | Rule catalog, check code, data-quality report |
| 03 SQL & Data Modeling | Dimensional modelling, grain, window functions, layered SQL, dense date grids | M-5a, R-2a/b, M-4a, M-7e | SQL models, data contracts, reconciliation results |
| 04 Exploratory Demand Analysis | Decomposition, promotion and holiday effects, segment comparison, intermittency | M-1a–f, M-2a–d, RO-3 | EDA notebook and a findings summary that feeds the forecasting logic |
| 05 Forecast Baselines | Naive, seasonal naive and moving average; rolling-origin backtesting; leakage | M-2, R-4, RO-4 | Baseline forecasts table and backtest results |
| 06 Statistical Models | ETS, STL, intermittent-demand methods | R-4 | Model comparison against the baselines |
| 07 ML Forecasting | Lag, rolling, calendar and promotion features; global models; leakage control | B-2f | A kept-or-rejected decision for the ML model, with evidence |
| 08 Forecast Evaluation | Choosing metrics; analysis by segment and horizon | M-3a, RO-1, RO-2, R-4e | Evaluation report showing where accuracy gets worse |
| 09 Root Cause Analysis | Triage, drill-down, error decomposition, evidence language | M-6b–d, M-3b, R-7 | RCA case studies and the recommendations log |
| 10 Monitoring | Accuracy tracking, drift, historical replay | M-3a, M-4c, RO-5 | Tracker tables and outputs from the replay runs |
| 11 Alerts / Trackers | Setting thresholds, avoiding alert fatigue, triage workflow | M-4c, M-4d | Alert rule config, alert log, discrepancy tracker |
| 12 Airflow (optional) | DAGs, idempotent tasks, backfill | B-2a, M-5d | DAG code and backfill run logs |
| 13 BigQuery | BigQuery SQL dialect, partitioning and clustering, cost control | M-5c, R-2c, B-2b, M-7e | BigQuery datasets and a bytes-processed comparison |
| 14 Looker Studio / Dashboard | Dashboard design for planners | M-4b, R-5, B-2c | Dashboard link, written spec, screenshots |
| 15 Testing & Reliability | Unit and integration tests, CI, reproducibility | RO-2, R-6 | Green CI and tests covering the critical logic |
| 16 Portfolio Polish & Final Audit | Storytelling, honest audit against the JD | R-7 | README and the final audit table from CLAUDE.md §20 |

---

## 11. Requirement Traceability

Status values at Phase 00:

- **Planned:** evidence is planned.
- **Planned (optional):** evidence is planned in Advanced scope.
- **Dataset-dependent:** whether it can be shown depends on the dataset chosen in D1.
- **Not project-replaceable:** a candidate attribute that no project can stand in for.

| ID | Target-role JD item | Type | DemandFlow evidence (planned) | Phase | Status | Limitation |
|---|---|---|---|---|---|---|
| RO-1 | Improve demand forecast accuracy | Role objective | Backtest improvement over the baselines, by segment | 05–08 | Planned | Compared with our own baselines only |
| RO-2 | Forecast reliability | Role objective | Bias and stability tracking, data-quality gates, tests | 02, 08, 10, 15 | Planned | Historical replay only |
| RO-3 | Analyze sales and demand patterns | Role objective | EDA and analysis marts | 04 | Planned | Sales data is censored and is not true demand |
| RO-4 | Develop forecasting logic | Role objective | Documented progression of forecasting logic | 05–07 | Planned | Method is our choice |
| RO-5 | Automated tools and monitoring | Role objective | CLI runs by as-of date, tracker, alerts | 10–12 | Planned | Replay only |
| RO-6 | Support inventory and fulfillment decisions | Role objective | Under- and over-forecast risk flags | 08–11 | Dataset-dependent | No inventory data |
| RO-7 | Demand met just-in-time | Role objective | Short-horizon daily forecasts, error by horizon | 05, 08 | Dataset-dependent | No lead-time or stock data |
| RO-8 | Practical forecasting solutions | Role objective | A model is kept only if it beats the baseline; runbook | 05–08, 16 | Planned | — |
| RO-9 | Improve product availability (cross-functionally) | Role objective | Written limitation; optional availability module | 04, optional | Dataset-dependent | No stockout labels in Favorita |
| M-1a | SKUs | Mission | SKU velocity and intermittency analysis | 04 | Planned | — |
| M-1b | Hubs | Mission | Hub (store) level analysis | 04 | Dataset-dependent | Stores stand in for hubs |
| M-1c | Categories | Mission | Family, class and perishable analysis | 04 | Planned | — |
| M-1d | Campaigns | Mission | Promotion uplift and retail events | 04 | Dataset-dependent | A promotion flag, not named campaigns; NaNs present |
| M-1e | Pricing | Mission | None in the primary dataset; optional module | optional | Dataset-dependent | **No price in Favorita** |
| M-1f | Seasonal events | Mission | Holiday, event and payday analysis | 04 | Planned | Ecuadorian calendar |
| M-2a | Trends | Mission | Decomposition and trend features | 04–07 | Planned | — |
| M-2b | Seasonality | Mission | Seasonal profiles and seasonal-naive baseline | 04–07 | Planned | ~4 annual cycles |
| M-2c | Outliers | Mission | Detection plus a flag-and-cap policy | 02, 04, 05 | Planned | — |
| M-2d | Demand anomalies | Mission | Anomaly flags checked against a known disruption | 04, 10 | Planned | — |
| M-3a | Monitor forecast accuracy | Mission | Accuracy tracker by as-of × segment × horizon | 08, 10 | Planned | — |
| M-3b | Actionable recommendations | Mission | Recommendations log | 09–11, 16 | Planned | Owners are fictional |
| M-4a | Automated datasets | Mission | Layered marts with contracts | 01, 03 | Planned | — |
| M-4b | Automated dashboards | Mission | Looker Studio, with a report as fallback | 14 | Planned | Sandbox expiry (D7) |
| M-4c | Automated trackers | Mission | Accuracy and investigation trackers | 10–11 | Planned | — |
| M-4d | Automated alerts | Mission | Rule engine and alert log | 11 | Planned | File delivery by default |
| M-5a | SQL | Mission | All transformations and checks | 02–03, 08–11, 13 | Planned | — |
| M-5b | Python | Mission | Package and CLI | 01–15 | Planned | — |
| M-5c | BigQuery | Mission | BigQuery marts | 13 | Planned | Called "a plus" in Requirements |
| M-5d | Automate repetitive processes | Mission | Single-command runs, optional DAG | 10–12 | Planned | — |
| M-6a | Data issues | Mission | Data-quality catalog and gates | 02 | Planned | — |
| M-6b | Forecast discrepancies | Mission | Discrepancy rules and tracker | 09–11 | Planned | — |
| M-6c | Root-cause analysis | Mission | RCA workflow and case studies | 09 | Planned | Correlation is not causation |
| M-6d | Work with relevant teams to resolve | Mission | Routing to an owner role, resolution status | 09–11 | Not project-replaceable | Roles are simulated |
| M-7a | Partner with Demand Planning | Mission | Use-case document | 09–11, 16 | Not project-replaceable | Simulated perspective |
| M-7b | Partner with Supply Chain | Mission | Use-case document and risk flags | 09–11, 16 | Not project-replaceable | Simulated perspective |
| M-7c | Partner with Data Engineering | Mission | Data contracts and data-quality tickets | 02–03, 09 | Not project-replaceable | Simulated perspective |
| M-7d | Partner with Data Science | Mission | Evaluation framework and model findings | 05–09 | Not project-replaceable | Simulated perspective |
| M-7e | Scalable solutions | Mission | Columnar processing, as-of and incremental design, global model, BigQuery partitioning | 03, 07, 13 | Planned | Public-dataset scale, not enterprise |
| R-1 | 1–3 years of experience | Requirement | None | — | Not project-replaceable | — |
| R-2a | Strong SQL | Requirement | SQL layer | 02–03, 08–11, 13 | Planned | — |
| R-2b | Large datasets | Requirement | ~125M-row processing | 01–03, 13 | Dataset-dependent | Skill, not professional experience |
| R-2c | BigQuery is a plus | Requirement | BigQuery port | 13 | Planned | Not mandatory |
| R-3 | Python for analysis and automation | Requirement | Package, notebooks, CLI | 01–15 | Planned | — |
| R-4a | Forecasting | Requirement | Phases 05–07 | 05–07 | Planned | — |
| R-4b | Seasonality | Requirement | EDA and models | 04–07 | Planned | — |
| R-4c | Trends | Requirement | EDA and models | 04–07 | Planned | — |
| R-4d | Outliers | Requirement | Data quality, EDA, treatment policy | 02, 04 | Planned | — |
| R-4e | Forecast accuracy | Requirement | Evaluation framework | 08 | Planned | — |
| R-5 | Dashboards, reporting automation, data products, monitoring tools | Requirement | Dashboard, report, tracker, alerts | 10–14 | Planned | Capability, not professional experience |
| R-6 | Analytical and problem-solving skill; attention to detail | Requirement | Data-quality rigour, reconciliation, tests, decision log | All | Planned | Partly demonstrable |
| R-7 | Clear business insights and recommendations | Requirement | Findings summaries, RCA memos, recommendations | 04, 08–11, 16 | Planned | Partly demonstrable |
| R-8a | Fast-paced environment | Requirement | — | — | Not project-replaceable | — |
| R-8b | Collaborating across teams | Requirement | Artifacts ready for handover | All | Not project-replaceable | — |
| B-1 | Experience in e-commerce, quick commerce, retail, FMCG or supply chain | Bonus | Exposure to grocery-retail data | 01–16 | Not project-replaceable | Exposure only; supermarket data, not quick commerce |
| B-2a | Airflow | Bonus | Local DAG with backfill | 12 | Planned (optional) | Local only |
| B-2b | GCP | Bonus | BigQuery | 13 | Planned | Free tier |
| B-2c | Looker Studio | Bonus | Dashboard | 14 | Planned | — |
| B-2d | Superset | Bonus | Not planned by default | — | Planned (optional) | Duplicates Looker Studio |
| B-2e | Git | Bonus | Whole repository and CI | 00–16 | Planned | — |
| B-2f | Machine-learning forecasting | Bonus | LightGBM global model | 07 | Planned | Kept only if justified |

---

## 12. Risks and Trade-offs

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| K1 | **Public dataset limitations.** Favorita is Ecuadorian supermarket data from 2013–2017. It is not quick commerce and does not reflect the target company's actual regional calendar. | Findings do not carry over to the target company's real context | Frame the project as a method demonstration, not as insight into the target company's real operations. State this in the README. |
| K2 | **Missing JD dimensions.** Pricing is absent, and campaigns exist only as a promotion flag. | M-1e is not demonstrated; M-1d is only partly | Record as *Limited by dataset*. Offer the optional pricing module. Never use oil price as a stand-in for pricing. |
| K3 | **Sales are not demand (censoring).** Zero-sales rows are omitted and stockouts are invisible. | Forecasts predict sales, and under-forecasting can reinforce itself | Label outputs as sales forecasts. Add `is_imputed_zero`. Write up the limitation. Optional FreshRetailNet module. |
| K4 | **A missing row could be zero sales or an unlisted item.** | Zero-filling everything biases forecasts down for delisted or not-yet-launched items | Zero-fill only inside an item-hub's active window (first sale to last sale). Document the rule in Phase 02 and 03. |
| K5 | **Forecasting uncertainty.** Hub × SKU × day series are often intermittent. | Accuracy per SKU per day will look poor, and MAPE is undefined when actuals are zero | Use WAPE and bias as the main metrics, aggregated by segment. Report MAPE only at levels without zeros. Compare against baselines, not against absolute targets. |
| K6 | **Leakage.** Promotions assumed known in advance; features built with future data. | Accuracy is inflated | Features only use data up to the as-of date. Assumption S6 is stated explicitly. Tests check the as-of cutoffs. |
| K7 | **Cloud cost.** BigQuery overrun; managed Airflow. | Unexpected charges | Sandbox or strict quotas, `maximum_bytes_billed`, a budget alert, and no managed Airflow |
| K8 | **Sandbox expiry** breaks the dashboard after 60 days | The portfolio link dies | Decision D7 |
| K9 | **Over-engineering** | Time spent on tooling rather than JD evidence | Every component must map to a JD item in §2. Optional phases can be cut, with the reason written down. |
| K10 | **Compute limits.** ~125M rows on a laptop or in this cloud container. | Out-of-memory failures, slow runs | DuckDB and Parquet, a scoped modelling subset, and recorded memory and runtime. Confirm hardware (D10). |
| K11 | **Environment network policy.** During this planning phase the container **blocked `www.kaggle.com`**, `huggingface.co` and `arxiv.org`. | Phase 01 cannot download data here as currently configured | Allow the Kaggle hosts in the environment's network settings, or run Phase 01 locally (D10) |
| K12 | **Licence terms.** Kaggle competition data probably restricts redistribution. | Committing raw data may breach the terms | Raw data stays out of Git (`.gitignore`). Commit code and aggregate results only. Check the terms in Phase 01. |
| K13 | **Collaboration with the target company's real teams cannot be reproduced** | M-6d and M-7 are only simulated | Label stakeholder perspectives as simulated. Never claim real collaboration. |
| K14 | **The experience requirement cannot be replaced** | R-1 and B-1 stay unmet | State this plainly in the README and the final audit |
| K15 | **Misattribution.** Project decisions could end up presented as the target company's practice. | Credibility risk in interviews | Use the labels from this document. The Phase 16 audit checks for it. |
| K16 | **Re-identification.** The target company's real name is deliberately withheld from this public repository (see the notice in `CLAUDE.md` §1). It could be reintroduced by accident in code, comments, commit messages, or a future edit. | Would defeat the anonymization the user asked for | Refer to it only as "the target company" or "the target role" anywhere in the repo. Keep the verbatim source and identity in `.private/`, which is git-ignored. Also note: "Astro" is separately the name of Astronomer's managed-Airflow product — write "Airflow" in this project, never "Astro", to avoid confusion in documentation and search. |
| K17 | **Arbitrary alert thresholds** | Alert fatigue, or alerts that never fire | Derive thresholds from the backtest distribution. Replay over a known disruption to check them. |
| K18 | **Replay is not live operation.** No late-arriving or corrected data. | Monitoring looks cleaner than it would in reality | Document it. Optionally inject a simulated late-data scenario during Phase 10–11 testing. |

---

## 13. Proposed Folder Structure

This is planned only. Apart from `CLAUDE.md` and this document, **nothing has been created**. Each directory is created in the phase that needs it.

```
Demand-Forecasting-Analysis/
├── CLAUDE.md                        # persistent project context (exists)
├── README.md                        # Phase 16 (short stub may come earlier)
├── pyproject.toml                   # Python package + tool config        (Phase 01)
├── Makefile                         # make ingest / dq / transform / run AS_OF=...
├── .gitignore                       # excludes data/, credentials, caches
├── .github/workflows/ci.yml         # lint + tests on fixtures            (Phase 15)
├── configs/
│   ├── project.yaml                 # scope, horizon, replay dates
│   └── alert_rules.yaml             # thresholds                          (Phase 11)
├── data/                            # git-ignored
│   ├── raw/                         # downloads, untouched + checksums
│   ├── parquet/                     # raw layer as Parquet
│   └── warehouse/demandflow.duckdb
├── sql/
│   ├── staging/
│   ├── intermediate/
│   ├── marts/
│   ├── quality/                     # DQ assertion queries
│   ├── rca/                         # drill-down templates
│   └── bigquery/                    # dialect-specific overrides (Phase 13)
├── src/demandflow/
│   ├── cli.py                       # demandflow run --as-of ...
│   ├── config.py
│   ├── logging_utils.py
│   ├── ingest/
│   ├── quality/
│   ├── transform/                   # SQL runner
│   ├── features/
│   ├── forecasting/                 # baselines.py, statistical.py, ml.py
│   ├── evaluation/                  # metrics.py, backtest.py
│   ├── monitoring/
│   ├── alerts/
│   ├── rca/
│   └── reporting/
├── notebooks/                       # numbered narrative notebooks (EDA, model review)
├── orchestration/airflow/dags/      # optional (Phase 12)
├── dashboards/                      # Looker Studio spec + screenshots (Phase 14)
├── reports/                         # generated outputs (figures, alert digests)
├── docs/
│   ├── 00_requirement_analysis_and_system_plan.md   # this document (exists)
│   ├── dataset_card.md              # Phase 01
│   ├── data_contracts/              # Phase 03
│   ├── data_quality/                # Phase 02 rule catalog + report
│   ├── decisions/                   # short decision records (ADR style)
│   ├── rca/                         # RCA case studies (Phase 09)
│   ├── stakeholders/                # simulated stakeholder use cases
│   └── phase_reports/               # review package per phase
└── tests/
    ├── fixtures/                    # tiny hand-made data, safe to commit
    ├── unit/
    └── integration/
```

---

## 14. Before We Code

> **Update, 2026-09-27:** the decisions below have been reviewed and finalized by the
> project owner. The final positions, the approved controlled-development sampling
> methodology for Favorita, the hardware/resource assessment, and a critical
> reassessment of the whole plan are recorded in
> [`docs/decisions/0001-phase00-decisions-and-scope.md`](decisions/0001-phase00-decisions-and-scope.md).
> The table below is left as originally written, as the historical record of what was
> proposed at the end of Phase 00.

### 14.1 Decisions that need your approval

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | Primary dataset | Favorita / M5 / other | **Favorita.** Choose M5 only if pricing matters more to you than campaigns and hub breadth. |
| **D2** | Handling the pricing gap | (a) Document as *Limited by dataset*. (b) Add a secondary pricing module later. | **(a) now.** Reconsider (b) after Phase 11, if time allows. |
| **D3** | Planning grain, horizon and cadence | hub × SKU × day, 14-day horizon, weekly as-of runs (S3–S5) | **Approve as an [ASSUMPTION]** |
| **D4** | Modelling scope | SQL layer covers **all** the data. Forecasting covers a **scoped subset**, chosen in Phase 04 by stated criteria (for example selected families including perishables, and item-hub pairs with enough history). | **Approve the principle now.** The exact subset is chosen with evidence in Phase 04. |
| **D5** | Local stack | Python + DuckDB + Parquet | **Approve** |
| **D6** | SQL framework | Plain layered SQL with a small Python runner / dbt-duckdb | **Plain SQL.** dbt is not in the JD. Tell me if you want dbt for the analytics-engineering signal. |
| **D7** | BigQuery mode | Sandbox (no card, 60-day expiry, no DML) / free tier with billing plus a budget alert | **Sandbox for development.** Decide before Phase 14 whether you want a durable public dashboard. |
| **D8** | Dashboard tool | Looker Studio / Superset / local report only | **Looker Studio**, with a local report as the MVP fallback |
| **D9** | Airflow | Optional Phase 12 in local Docker / replace with CLI + Makefile | **Keep it optional.** Decide after Phase 11. |
| **D10** | Where the pipeline runs | Your laptop / this cloud container | Tell me your laptop's RAM and free disk. 16 GB RAM and ~20 GB free disk is comfortable [estimate]. In this container, Kaggle is currently blocked (K11). |
| **D11** | Public repository contents | Keep `CLAUDE.md`, which contains the full JD and the working rules, in a public repository? | Your call. It shows discipline, but it also shows which job you are targeting. |

### 14.2 Assumptions to confirm

- **A1:** Stores are treated as hubs (S2).
- **A2:** Promotion and holiday calendars are known at forecast time (S6, S7).
- **A3:** A missing hub × SKU × day row inside an item's active window means **zero sales**. It is flagged and does not mean zero demand (K3, K4).
- **A4:** Negative `unit_sales` are returns. They are kept in staging and handled by an explicit rule in Phase 02.
- **A5:** WAPE and bias are the main metrics. MAE and RMSE are secondary. MAPE is used only at levels with no zero actuals.
- **A6:** Under-forecast stands in for stockout risk and over-forecast for waste risk (S10).
- **A7:** Alert thresholds are derived from the data, not from any KPI of the target company (S12).
- **A8:** Time-aware validation only: rolling-origin backtests plus a final holdout made of the last weeks of history. The Kaggle test file has no labels, so it is not used for evaluation.

### 14.3 Dataset characteristics that matter

These are what Phase 01 must check on the real files:

1. **Grain and keys.** Is (date, store, item) unique? How many duplicates are there?
2. **Time coverage.** The exact date range, missing dates (for example 25 December), and store opening and closing dates.
3. **What a zero means.** How many rows are missing, and the active window of each item-hub pair.
4. **Promotion coverage.** The share and time span of `onpromotion` NaNs.
5. **Dimension coverage.** Counts of hubs, SKUs, families and classes, and the holiday/event types that exist.
6. **Value validity.** Negative and fractional sales, extreme values.
7. **Size against hardware.** File sizes, row counts, memory needed for the modelling scope.
8. **Licence and terms.** Whether redistribution is allowed and whether attribution is required.

### 14.4 What Phase 01 (Dataset) will do

**Will do:**
- Set up a minimal Python project skeleton for acquisition only.
- Download the approved dataset through the Kaggle API, using your own credentials after you accept the competition rules.
- Record SHA-256 checksums.
- Convert the files to Parquet with **no changes to any values**.
- Profile the data: row counts, schema, date ranges, key uniqueness, null shares.
- Write `docs/dataset_card.md`, covering:
  - source, licence terms and citation;
  - grain and fields;
  - **JD-dimension coverage checked against the actual data**;
  - known limitations;
  - which of the **[VERIFY]** facts in this document were confirmed or corrected.
- Add `.gitignore` rules so that raw data never reaches Git.

**Will not do:** clean or change data (Phase 02), build models or SQL marts (Phase 03 onward).

**Prerequisites for Phase 01 in this cloud environment:**
- The environment's network policy currently denies **`www.kaggle.com`**. Kaggle file downloads may also need **`storage.googleapis.com`** [VERIFY].
- To allow them, edit Network access in the environment settings: open the cloud environment menu in the session title bar, choose **Edit**, and add those hosts or pick a broader access level. Access levels are described at <https://code.claude.com/docs/en/claude-code-on-the-web>.
- Kaggle credentials go in the same settings, as environment variables **`KAGGLE_USERNAME`** and **`KAGGLE_KEY`**. Never paste them into chat. A new session picks them up.
- The alternative is to run Phase 01 on your own machine.

---

*End of Phase 00. Phase 01 has not been started.*
