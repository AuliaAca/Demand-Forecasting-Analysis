#!/usr/bin/env bash
# Phase 13 -- loads the raw Parquet files Phase 01's convert step already
# produces (plus Phase 01's dev_scope_items.csv) into native BigQuery
# tables, so sql/bigquery/staging/*.sql has something to read FROM.
#
# NEVER RUN in this sandbox: there is no real GCP project or billing
# account here (the same real-access gap disclosed since Phase 01's "no
# Kaggle credentials"; see docs/phase_reports/phase13.md). This script is
# written and documented, not executed -- run it for real once real GCP
# access and a real $DEMANDFLOW_DATA_DIR/parquet/ exist.
#
# Parquet is self-describing, so `bq load` needs no explicit schema --
# BigQuery infers types directly from the Parquet file's own metadata.
# `bq load` accepts a local file path directly for files under its size
# threshold (the dev-scope-sized parquet files this project produces);
# the full, real Favorita train.parquet is large enough that a real run
# should stage it in Cloud Storage first (`gcloud storage cp`) and load
# from the gs:// URI instead -- both invocations are shown below.
#
# Usage:
#   PROJECT=my-gcp-project DATASET=demandflow ./scripts/bigquery_load_raw.sh

set -euo pipefail

: "${PROJECT:?Set PROJECT to your GCP project id}"
: "${DATASET:?Set DATASET to the target BigQuery dataset (e.g. demandflow)}"
: "${DEMANDFLOW_DATA_DIR:?Set DEMANDFLOW_DATA_DIR to the same data root the Phase 01 convert step used}"

PARQUET_DIR="${DEMANDFLOW_DATA_DIR}/parquet"
DEV_SCOPE_CSV="${DEMANDFLOW_DATA_DIR}/dev_scope/dev_scope_items.csv"

bq mk --dataset --location=US "${PROJECT}:${DATASET}" 2>/dev/null || true

# Small/medium files: load directly from the local filesystem.
for table in stores items holidays_events oil transactions; do
    bq load --source_format=PARQUET --replace \
        "${PROJECT}:${DATASET}.raw_${table}" \
        "${PARQUET_DIR}/${table}.parquet"
done

# train.parquet: the one genuinely large file (the full real dataset is
# ~125M rows). On the dev-scope/fixture size used throughout this project
# a direct local load also works; a real full-dataset run should stage it
# in GCS first:
#   gcloud storage cp "${PARQUET_DIR}/train.parquet" "gs://${BUCKET}/train.parquet"
#   bq load --source_format=PARQUET --replace \
#       "${PROJECT}:${DATASET}.raw_train" "gs://${BUCKET}/train.parquet"
bq load --source_format=PARQUET --replace \
    "${PROJECT}:${DATASET}.raw_train" \
    "${PARQUET_DIR}/train.parquet"

# dev_scope_items.csv (Phase 01's frozen, reproducible item selection) --
# small, and a CSV rather than Parquet, so schema is auto-detected instead.
bq load --source_format=CSV --autodetect --replace \
    "${PROJECT}:${DATASET}.raw_dev_scope_items" \
    "${DEV_SCOPE_CSV}"

echo "Loaded raw tables into ${PROJECT}:${DATASET}. Next: render and run"
echo "sql/bigquery/{staging,intermediate,marts}/*.sql in that order"
echo "(see src/demandflow/bigquery/validate_sql.py's render_sql())."
