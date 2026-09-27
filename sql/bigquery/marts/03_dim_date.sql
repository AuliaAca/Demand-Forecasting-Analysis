-- BigQuery port of sql/marts/03_dim_date.sql. Same standard date
-- dimension as the DuckDB version, with the dialect differences already
-- documented in sql/bigquery/intermediate/01_int_calendar_by_store.sql
-- (day-of-week normalization, GENERATE_DATE_ARRAY, DATE_TRUNC argument
-- order) applied consistently here, plus one more:
--
-- **DuckDB's EXTRACT(week FROM date) already returns the ISO 8601 week
-- number** (matching this column's name, iso_week). BigQuery's plain
-- EXTRACT(WEEK FROM date) returns a Sunday-based, non-ISO week number
-- (0-53) -- a different value that would silently break the "iso_week"
-- name's meaning. EXTRACT(ISOWEEK FROM date) is BigQuery's actual ISO
-- 8601 week extraction, matching the DuckDB column's real semantics.
--
-- No PARTITION BY / CLUSTER BY -- same reasoning as dim_hub.sql / dim_sku.sql:
-- a date dimension spanning even the full ~4.6-year real history is at
-- most a few thousand rows, too small for partitioning to help.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.dim_date` AS
WITH bounds AS (
    SELECT MIN(date) AS min_date, MAX(date) AS max_date
    FROM `__PROJECT__.__DATASET__.stg_sales`
),
calendar AS (
    SELECT date
    FROM UNNEST(GENERATE_DATE_ARRAY(
        (SELECT min_date FROM bounds), (SELECT max_date FROM bounds), INTERVAL 1 DAY
    )) AS date
)
SELECT
    date,
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    EXTRACT(DAY FROM date) AS day_of_month,
    EXTRACT(DAYOFWEEK FROM date) - 1 AS day_of_week,
    EXTRACT(DAYOFWEEK FROM date) - 1 IN (0, 6) AS is_weekend,
    EXTRACT(ISOWEEK FROM date) AS iso_week,
    FORMAT_DATE('%B', date) AS month_name,
    (EXTRACT(DAY FROM date) = 15
        OR date = DATE_SUB(DATE_ADD(DATE_TRUNC(date, MONTH), INTERVAL 1 MONTH), INTERVAL 1 DAY)
    ) AS is_payday
FROM calendar;
