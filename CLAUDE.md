# CLAUDE.md
# DemandFlow — Persistent Project Context

> IMPORTANT — PUBLIC-REPOSITORY NOTICE:
> This project was scoped against a real job description ("the target JD"), supplied
> privately by the project owner for a Data Analyst role at a real quick-commerce
> company. That company's name, exact wording, and identifying narrative are
> **not reproduced in this public repository**.
>
> Section 1 below is an **anonymized, paraphrased restatement** of the target JD:
> same requirement categories, same scope, no verbatim company copy and no
> company name. The verbatim original is kept locally, outside version control
> (`.private/JD_SOURCE_VERBATIM.md`, git-ignored) for the project owner's own
> reference. Nothing in this repository, its commits, or its docs should ever
> reintroduce that file or the company's name.
>
> Treat Section 1 as the source of truth for scoping. Do not invent, embellish,
> or silently add requirements beyond what is paraphrased there.
>
> Phase prompts should reference this file rather than repeating the JD.

---

# 1. TARGET ROLE PROFILE — ANONYMIZED SOURCE OF TRUTH

### Company context (paraphrased, non-identifying)

The target JD is for a **quick-commerce company that delivers groceries and
everyday essentials directly to consumers, with very fast (near-immediate)
delivery as its core value proposition**. The posting describes the company as
young, fast-growing, well-funded, and as culturally positioning itself as
fast-moving, ambitious, and technology-driven.

This is company background, not a technical requirement. In particular:
- **[DECISION]** DemandFlow does not derive technical requirements from the
  "very fast delivery" positioning (for example, "sub-hourly forecasting is
  required"). The target JD's job description and requirements sections, below,
  state no such requirement.

### About the position (paraphrased)

The role is a **Data Analyst supporting a Demand Planning function**, focused on
improving demand forecast **accuracy** and **reliability**. The analyst is
expected to analyze sales and demand patterns, develop forecasting logic, and
build automated tools and monitoring that support inventory and fulfillment
decisions — with the underlying goal of meeting customer demand on a
just-in-time basis. The posting frames success as turning data into practical
forecasting solutions and working cross-functionally to improve product
availability.

### Job description / missions (paraphrased, same scope as the original)

The role's stated missions are to:

- Analyze demand patterns across **SKUs, hubs, categories, campaigns, pricing,
  and seasonal events**.
- Improve forecasting logic by identifying **trends, seasonality, outliers, and
  demand anomalies**.
- Monitor forecast accuracy and turn findings into **actionable
  recommendations**.
- Build automated **datasets, dashboards, trackers, and alerts** to make
  planning faster and smarter.
- Use **SQL, Python, and BigQuery** to transform data and automate repetitive
  processes.
- Investigate data issues and forecast discrepancies, perform root-cause
  analysis, and work with relevant teams to resolve them.
- Partner with **Demand Planning, Supply Chain, Data Engineering, and Data
  Science** to build scalable solutions.

### Requirements (paraphrased, same scope as the original)

The stated requirements are:

- **1–3 years of experience** in Data Analytics, BI, Supply Chain Analytics,
  Analytics Engineering, or a similar role.
- Strong **SQL** and experience working with large datasets; **BigQuery is
  called out as a plus**, not mandatory.
- Comfortable using **Python** for analysis and automation.
- Understanding of **forecasting, seasonality, trends, outliers, and forecast
  accuracy**.
- Experience with dashboards, reporting automation, data products, or
  monitoring tools.
- Strong analytical and problem-solving skills with attention to detail.
- Able to turn complex analysis into **clear business insights and
  recommendations**.
- Comfortable in a fast-paced environment, collaborating across teams.

### Bonus points (paraphrased, same scope as the original)

Bonus signals named in the posting:

- Experience in **e-commerce, quick commerce, retail, FMCG, or supply chain**.
- Exposure to **Airflow, GCP, Looker Studio, Superset, Git, or machine-learning
  forecasting**.

---

# 2. HOW TO USE THIS ROLE PROFILE

The purpose of DemandFlow is to build a portfolio project that demonstrates
capabilities relevant to the target role above.

Do NOT claim:
- the target company's internal data
- the target company's internal systems
- the target company's internal forecasting logic
- the target company's internal supply-chain processes
- the target company's internal operational practices
- the target company's name or identity anywhere in this repository

The project is an industry-inspired simulation.

When translating the role profile into project requirements, preserve the
distinction between:

### A. Exact JD requirement
Directly stated in Section 1 above.

### B. Project implementation decision
A technical choice we make to demonstrate the requirement.

### C. Project assumption
A simulation assumption because we do not have the target company's internal
data.

Never present B or C as a requirement of the target role.

---

# 3. JD → CAPABILITY → PROJECT EVIDENCE

Use this framework when planning:

> JD requirement → capability → DemandFlow component → evidence

Do not create a component merely because a technology sounds impressive.

## 3.1 Demand pattern analysis

The role profile explicitly requires analysis across:
- SKUs
- hubs
- categories
- campaigns
- pricing
- seasonal events

DemandFlow should determine which of these are actually available in the
selected public dataset.

If a dimension is unavailable:
- document the limitation
- do not fabricate it
- do not claim the requirement was fully demonstrated

## 3.2 Forecasting logic

The role profile explicitly mentions:
- trends
- seasonality
- outliers
- demand anomalies
- forecast accuracy

DemandFlow should demonstrate these concepts through appropriate analysis and
forecasting work.

The exact forecasting method is NOT specified. Model selection must therefore
be justified by project evidence rather than falsely attributed to the target
role.

## 3.3 Forecast monitoring and recommendations

The role profile explicitly requires:
- monitoring forecast accuracy
- turning findings into actionable recommendations

DemandFlow should therefore connect:
forecast → evaluation → monitoring → finding → recommendation.

## 3.4 Automated analytical tools

The role profile explicitly mentions:
- datasets
- dashboards
- trackers
- alerts

The exact implementation technology is not specified for these four items.
Choose technology based on usefulness, cost, and project scope.

## 3.5 SQL / Python / BigQuery

The role profile explicitly names:
- SQL
- Python
- BigQuery

SQL and Python are explicit requirements.

BigQuery is explicitly described as a plus in the requirements.

Do not claim that the role requires BigQuery as a mandatory skill.

## 3.6 Data issues and forecast discrepancies

The role profile explicitly requires:
- investigation of data issues
- investigation of forecast discrepancies
- root-cause analysis
- working with relevant teams to resolve them

DemandFlow should contain a reproducible investigation/RCA workflow where the
public data allows it.

## 3.7 Cross-functional collaboration

The role profile explicitly names:
- Demand Planning
- Supply Chain
- Data Engineering
- Data Science

DemandFlow cannot reproduce real organizational collaboration.

Instead, document the relevant stakeholder/use-case perspective where
appropriate. Never claim real collaboration with these teams.

## 3.8 Scalable solutions

"Build scalable solutions" is explicitly in the role profile.

Demonstrate scalability through appropriate architecture, data modeling,
reusable transformations, automation, or efficient processing where
justified.

Do not manufacture enterprise-scale infrastructure just to claim scalability.

---

# 4. REQUIREMENTS THAT ARE EXPERIENCE / QUALIFICATION SIGNALS

The role profile includes:

- 1–3 years of experience in Data Analytics, BI, Supply Chain Analytics,
  Analytics Engineering, or a similar role.

This is a candidate experience requirement, not something the DemandFlow
project can truthfully replace with "equivalent years of experience."

The project can demonstrate relevant capabilities, but it must not claim that
the project satisfies the stated years-of-experience requirement.

The role profile also asks for:
- strong analytical and problem-solving skills
- attention to detail
- ability to turn complex analysis into clear business insights and
  recommendations
- comfort working in a fast-paced environment
- collaborating across teams

These are partly demonstrated through project work, documentation, reasoning,
and communication, but they should not be falsely presented as proven
professional experience.

---

# 5. BONUS POINTS — EXACT SCOPE

The role profile says bonus points include experience in:
- e-commerce
- quick commerce
- retail
- FMCG
- supply chain

or exposure to:
- Airflow
- GCP
- Looker Studio
- Superset
- Git
- machine-learning forecasting

These are bonus signals, not mandatory requirements.

DemandFlow may use some of them when justified.

Do not force all bonus technologies into the project.

---

# 6. DEMANDFLOW PROJECT

## Working title

**DemandFlow — Retail Demand Forecasting & Planning Intelligence Platform**

The project simulates an analytics workflow supporting demand planning for a
fictional retail / quick-commerce business.

Initial conceptual flow:

Raw Retail Data
↓
Data Validation
↓
SQL Transformation
↓
Analytical Data Layer / Warehouse
↓
Demand Analysis
↓
Forecasting
↓
Forecast Evaluation
↓
Anomaly / Discrepancy Investigation
↓
Root-Cause Analysis
↓
Monitoring
↓
Alerts / Trackers
↓
Dashboard
↓
Business Recommendations

This is a proposed architecture, NOT part of the target role profile.

The architecture may change if a better design is justified.

---

# 7. PROJECT BUSINESS QUESTIONS

Potential questions should be derived from the role profile and available
data.

Examples:
- How does demand vary across available SKUs, hubs/stores, categories,
  campaigns, pricing, and seasonal events?
- What trends and seasonal patterns exist?
- Where are outliers or demand anomalies?
- How accurate is the forecast?
- Where is forecast accuracy deteriorating?
- What forecast discrepancies require investigation?
- What evidence may explain a discrepancy?
- What actionable recommendation follows from the evidence?

Only answer questions that the selected dataset can actually support.

---

# 8. DATASET RULE

Investigate public retail / grocery datasets.

Potential candidates may include:
- Corporación Favorita Grocery Sales Forecasting
- M5 Forecasting Accuracy
- other suitable public retail datasets

These are dataset candidates, NOT requirements of the target role.

Select a dataset based on actual fit with the role profile:
- demand/sales data
- product/SKU dimension
- store/hub-like dimension
- category
- campaigns/promotions
- pricing
- seasonal/calendar information
- sufficient time coverage
- suitable granularity
- sufficient scale
- reproducibility

If a dataset lacks a required dimension, document the limitation.

---

# 9. COST PRINCIPLE

Prefer free/local solutions when they can demonstrate the required capability.

Cloud tools should be introduced only when they add meaningful evidence.

Consider:
- local processing
- free tiers
- cloud cost
- reproducibility
- actual learning value

Do not add infrastructure only for appearance.

---

# 10. FORECASTING PRINCIPLE

The target role requires understanding of forecasting and forecast accuracy,
but does NOT prescribe a specific algorithm.

Therefore start with defensible baselines and increase complexity only when
justified.

Possible progression:
1. Naive
2. Seasonal Naive
3. Moving Average / statistical model where justified
4. ML forecasting where justified

Use time-aware validation.

Do not randomly split time-series data without a defensible reason.

---

# 11. METRICS

Possible forecast metrics:
- MAE
- RMSE
- WAPE
- Forecast Bias
- MAPE when meaningful

Metric choice must be justified by data characteristics and business use.

Evaluate useful segments when the data supports them.

---

# 12. DATA QUALITY

Data issues are explicitly part of the role profile.

Check for relevant issues such as:
- missing dates
- duplicates
- null keys
- invalid values
- inconsistent grain
- date gaps
- suspicious demand values
- missing dimensions

Do not silently remove problematic records.

Document:
- rule
- finding
- severity
- consequence
- handling decision

---

# 13. RCA / EVIDENCE RULE

A forecast discrepancy or anomaly is an investigation trigger.

Do not automatically treat correlation as causation.

Use evidence-based language such as:
- associated with
- consistent with
- possible contributor
- requires further investigation

---

# 14. ENGINEERING PRINCIPLES

Prefer:
- reproducibility
- modular code
- clear data contracts/grain
- validation
- logging
- testing
- automation
- maintainability
- cost awareness

Do not over-engineer.

---

# 15. IMPLEMENTATION MODE

Claude Code may fully implement the current phase.

During an implementation phase Claude may:
- write code
- create/update files
- run tests/checks
- debug and fix issues within the current phase
- update documentation

Claude must:
- use `CLAUDE.md` as persistent context
- stay within the current phase
- stop before beginning the next phase
- clearly report what was done

The user reviews each completed phase before continuing.

---

# 16. STANDARD REVIEW PACKAGE

After each implementation phase, report:

## What was built
Concrete files/components.

## JD connection
Which exact requirement(s) from the role profile this phase provides evidence
for.

## Key decisions
Important choices and trade-offs.

## Validation
Tests/checks and results.

## Findings
Important technical/business findings.

## Limitations
Dataset limitations, assumptions, or incomplete requirements.

## What to review
Specific things the user should inspect.

## Interview questions
Questions the user should be able to answer.

Then STOP.

---

# 17. PHASES

00 — Requirement Analysis & System Planning
01 — Dataset
02 — Data Quality
03 — SQL & Data Modeling
04 — Exploratory Demand Analysis
05 — Forecast Baselines
06 — Statistical Models
07 — Machine Learning Forecasting
08 — Forecast Evaluation
09 — Root Cause Analysis
10 — Monitoring
11 — Alerts / Trackers
12 — Airflow
13 — BigQuery
14 — Looker Studio / Dashboard
15 — Testing & Reliability
16 — Portfolio Polish & Final Audit

Phase 00 is planning only.

Phases 01–16 implement only their assigned scope.

---

# 18. PHASE DISCIPLINE

Never silently start a later phase.

A later phase may be:
- unnecessary
- reduced
- deferred
- made optional

if evidence shows it does not add value.

But document the decision rather than silently skipping work.

---

# 19. HONESTY / SOURCE DISCIPLINE

When referring to the target role or company:

Use the anonymized role profile in Section 1 as the source.

Do not add:
- assumed internal tools
- assumed internal architecture
- assumed internal KPIs
- assumed internal forecasting methods
- assumed internal operational processes
- assumed internal data schema
- the target company's real name or identifying narrative

If something is not in Section 1, label it as:
- project decision
- assumption
- inference
- needs verification

---

# 20. FINAL AUDIT

At Phase 16, audit DemandFlow against every relevant part of the target role
profile:

### Position purpose
- demand forecast accuracy
- demand forecast reliability
- sales/demand pattern analysis
- forecasting logic
- automated tools
- monitoring
- inventory/fulfillment decision support
- product availability / just-in-time objective

### Missions
- SKU
- hub
- category
- campaign
- pricing
- seasonal events
- trends
- seasonality
- outliers
- demand anomalies
- forecast accuracy
- actionable recommendations
- datasets
- dashboards
- trackers
- alerts
- SQL
- Python
- BigQuery
- data issues
- forecast discrepancies
- root-cause analysis
- scalable solutions

### Requirements
- SQL / large datasets
- Python
- forecasting concepts
- dashboards/reporting automation/data products/monitoring
- analytical/problem-solving capability
- attention to detail
- clear business insights/recommendations
- cross-team collaboration capability

### Bonus
- e-commerce / quick commerce / retail / FMCG / supply chain
- Airflow / GCP / Looker Studio / Superset / Git / ML forecasting

For each item, classify:
- Demonstrated
- Partially demonstrated
- Not demonstrated
- Not applicable to project
- Limited by dataset

Do not turn this into a score or ranking.
