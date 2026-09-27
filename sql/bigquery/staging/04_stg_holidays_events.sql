-- BigQuery port of sql/staging/04_stg_holidays_events.sql. Identical
-- logic to the DuckDB version.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_holidays_events` AS
SELECT
    date,
    type,
    locale,
    locale_name,
    description,
    transferred
FROM `__PROJECT__.__DATASET__.raw_holidays_events`;
