# DemandFlow — Phase 01 automation.
#
# On the project owner's Windows machine, set DEMANDFLOW_DATA_DIR to a path
# under D:\ before running any target below (ADR 0001 §4.3), e.g. in
# PowerShell:
#     $env:DEMANDFLOW_DATA_DIR = "D:\dev\demandflow-data"
#     $env:KAGGLE_USERNAME = "..."
#     $env:KAGGLE_KEY = "..."
# These targets themselves are plain `python -m ...` calls and work
# identically on Windows, macOS, or Linux; `make` is a convenience wrapper,
# not a requirement — see docs/phase_reports/phase01.md for the equivalent
# direct commands if `make` isn't available.

.PHONY: install test lint smoke acquire convert profile select-scope dataset-card phase01 clean-smoke dq dq-report phase02 warehouse phase03 eda eda-report phase04 backtest backtest-report phase05 statistical-backtest statistical-report phase06 ml-backtest ml-report phase07 evaluate evaluate-report phase08 rca rca-report phase09 monitor monitor-report phase10 alerts alerts-report phase11 airflow-install airflow-validate airflow-test phase12 bigquery-validate phase13 dashboard phase14 phase15

install:
	pip install -e ".[dev]"

test:
	python -m pytest -q

lint:
	ruff check src/ tests/

# Same two checks .github/workflows/ci.yml runs on every push -- the
# repository's only automated proof the suite still runs clean on a fresh
# checkout, not just in a development sandbox (Phase 15).
phase15: lint test
	@echo "Phase 15 (testing & reliability): lint + full test suite passed."

# Runs the whole pipeline against the small, committed synthetic fixture —
# no Kaggle access needed. Proves the pipeline's plumbing end-to-end.
# Output: reports/phase01/fixture_smoke_test/ (git-ignored, regenerable).
smoke:
	python scripts/run_fixture_smoke_test.py

clean-smoke:
	rm -rf reports/fixture_smoke_test reports/phase01/fixture_smoke_test

# --- Real pipeline (needs Kaggle credentials + accepted competition rules) ---

acquire:
	python -m demandflow.ingest.acquire_favorita

convert:
	python -m demandflow.ingest.convert_to_parquet

profile:
	python -m demandflow.profiling.profile_favorita

select-scope:
	python -m demandflow.scope.select_dev_scope

dataset-card:
	python -m demandflow.reporting.generate_dataset_card

phase01: acquire convert profile select-scope dataset-card
	@echo "Phase 01 pipeline complete. See docs/dataset_card.md"

dq:
	python -m demandflow.quality.rules

dq-report:
	python -m demandflow.reporting.generate_dq_report

phase02: dq dq-report
	@echo "Phase 02 pipeline complete. See docs/data_quality/dq_report.md"

warehouse:
	python -m demandflow.transform.build_warehouse

phase03: warehouse
	@echo "Phase 03 pipeline complete. Warehouse at \$$DEMANDFLOW_DATA_DIR/warehouse/demandflow.duckdb"

eda:
	python -m demandflow.analysis.run_eda

eda-report:
	python -m demandflow.reporting.generate_eda_report

phase04: eda eda-report
	@echo "Phase 04 pipeline complete. See docs/eda_findings.md"

backtest:
	python -m demandflow.forecasting.run_backtest

backtest-report:
	python -m demandflow.reporting.generate_forecast_baselines_report

phase05: backtest backtest-report
	@echo "Phase 05 pipeline complete. See docs/forecast_baselines.md"

statistical-backtest:
	python -m demandflow.forecasting.run_statistical_backtest

statistical-report:
	python -m demandflow.reporting.generate_statistical_models_report

phase06: statistical-backtest statistical-report
	@echo "Phase 06 pipeline complete. See docs/statistical_models.md"

ml-backtest:
	python -m demandflow.forecasting.run_ml_backtest

ml-report:
	python -m demandflow.reporting.generate_ml_report

phase07: ml-backtest ml-report
	@echo "Phase 07 pipeline complete. See docs/ml_forecasting.md"

evaluate:
	python -m demandflow.evaluation.run_evaluation

evaluate-report:
	python -m demandflow.reporting.generate_evaluation_report

phase08: evaluate evaluate-report
	@echo "Phase 08 pipeline complete. See docs/forecast_evaluation.md"

rca:
	python -m demandflow.rca.run_rca

rca-report:
	python -m demandflow.reporting.generate_rca_report

phase09: rca rca-report
	@echo "Phase 09 pipeline complete. See docs/root_cause_analysis.md"

monitor:
	python -m demandflow.monitoring.run_monitoring

monitor-report:
	python -m demandflow.reporting.generate_monitoring_report

phase10: monitor monitor-report
	@echo "Phase 10 pipeline complete. See docs/monitoring.md"

alerts:
	python -m demandflow.alerts.run_alerts

alerts-report:
	python -m demandflow.reporting.generate_alerts_report

phase11: alerts alerts-report
	@echo "Phase 11 pipeline complete. See docs/alerts_and_tracker.md"

# --- Airflow (Phase 12, bonus) — isolated environment, see docs/phase_reports/phase12.md ---

airflow-install:
	python3 -m venv .venv-airflow
	.venv-airflow/bin/pip install -r requirements-airflow.txt \
		--constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.11.txt
	AIRFLOW_HOME="$$(pwd)/.airflow_home" AIRFLOW__CORE__DAGS_FOLDER="$$(pwd)/dags" \
		AIRFLOW__CORE__LOAD_EXAMPLES=False .venv-airflow/bin/airflow db migrate

airflow-validate:
	AIRFLOW_HOME="$$(pwd)/.airflow_home" AIRFLOW__CORE__DAGS_FOLDER="$$(pwd)/dags" \
		AIRFLOW__CORE__LOAD_EXAMPLES=False .venv-airflow/bin/airflow dags list-import-errors
	AIRFLOW_HOME="$$(pwd)/.airflow_home" AIRFLOW__CORE__DAGS_FOLDER="$$(pwd)/dags" \
		AIRFLOW__CORE__LOAD_EXAMPLES=False .venv-airflow/bin/airflow tasks list demandflow

airflow-test:
	.venv-airflow/bin/python -m pytest tests/unit/test_airflow_dag.py -v

phase12: airflow-validate airflow-test
	@echo "Phase 12 pipeline complete. See docs/phase_reports/phase12.md"

# --- BigQuery (Phase 13, bonus) — see docs/phase_reports/phase13.md ---

bigquery-validate:
	python -m demandflow.bigquery.validate_sql
	python -m pytest tests/unit/test_bigquery_sql.py -v

phase13: bigquery-validate
	@echo "Phase 13 pipeline complete. See docs/phase_reports/phase13.md"

dashboard:
	python -m demandflow.reporting.generate_dashboard

phase14: dashboard
	@echo "Phase 14 pipeline complete. See docs/dashboard.html"
