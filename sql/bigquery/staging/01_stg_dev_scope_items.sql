-- BigQuery port of sql/staging/01_stg_dev_scope_items.sql (Phase 13).
--
-- DuckDB reads configs/dev_scope_items.csv directly with read_csv_auto()
-- inline in SQL. BigQuery has no equivalent local-file scan; the CSV is
-- loaded once as a small native table (raw_dev_scope_items) via
-- scripts/bigquery_load_raw.sh, and this model is a typed pass-through --
-- the same raw -> staging shape every other staging model in this layer
-- uses, kept consistent rather than special-cased for one small file.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_dev_scope_items` AS
SELECT *
FROM `__PROJECT__.__DATASET__.raw_dev_scope_items`;
