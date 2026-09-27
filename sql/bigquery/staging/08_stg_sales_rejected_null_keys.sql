-- BigQuery port of sql/staging/08_stg_sales_rejected_null_keys.sql.
-- Identical logic to the DuckDB version.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_sales_rejected_null_keys` AS
SELECT *, 'null_key' AS reject_reason
FROM `__PROJECT__.__DATASET__.raw_train`
WHERE date IS NULL OR store_nbr IS NULL OR item_nbr IS NULL;
