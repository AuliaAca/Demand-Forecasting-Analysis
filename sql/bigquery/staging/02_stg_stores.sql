-- BigQuery port of sql/staging/02_stg_stores.sql. Typed, renamed
-- pass-through -- identical logic and syntax to the DuckDB version; only
-- the table reference is fully qualified for BigQuery.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_stores` AS
SELECT
    store_nbr,
    city,
    state,
    type AS store_type,
    cluster
FROM `__PROJECT__.__DATASET__.raw_stores`;
