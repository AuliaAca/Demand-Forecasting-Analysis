-- BigQuery port of sql/staging/05_stg_oil.sql. Identical logic to the
-- DuckDB version.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_oil` AS
SELECT
    date,
    dcoilwtico AS oil_price
FROM `__PROJECT__.__DATASET__.raw_oil`;
