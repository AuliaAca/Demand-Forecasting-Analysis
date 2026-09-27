-- BigQuery port of sql/staging/06_stg_transactions.sql. Identical logic
-- to the DuckDB version.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_transactions` AS
SELECT
    date,
    store_nbr,
    transactions AS transaction_count
FROM `__PROJECT__.__DATASET__.raw_transactions`;
