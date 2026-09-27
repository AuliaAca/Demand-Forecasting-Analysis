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

.PHONY: install test smoke acquire convert profile select-scope dataset-card phase01 clean-smoke dq dq-report phase02 warehouse phase03 eda eda-report phase04

install:
	pip install -e ".[dev]"

test:
	python -m pytest -q

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
