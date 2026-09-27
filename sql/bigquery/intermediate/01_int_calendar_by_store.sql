-- BigQuery port of sql/intermediate/01_int_calendar_by_store.sql. Same
-- holiday-resolution and payday logic as the DuckDB version, with three
-- genuine dialect differences fixed (not just re-typed):
--
-- 1. DuckDB's UNNEST(generate_series(...)) works directly in a SELECT
--    list. BigQuery's UNNEST() is a FROM-clause table operator: the
--    calendar CTE below uses `FROM UNNEST(GENERATE_DATE_ARRAY(...))`.
-- 2. **EXTRACT(dow FROM date) is NOT the same value in both engines.**
--    DuckDB's dow is 0=Sunday..6=Saturday. BigQuery's DAYOFWEEK is
--    1=Sunday..7=Saturday. `EXTRACT(DAYOFWEEK FROM date) - 1` normalizes
--    back to DuckDB's 0=Sunday..6=Saturday convention so the existing
--    `day_of_week IN (0, 6)` is_weekend check needs no change and this
--    table's meaning stays identical for anything that consumes it. This
--    is exactly the kind of silent, plausible-looking bug a naive
--    find-and-replace port would introduce.
-- 3. DuckDB's date_trunc('month', date) takes (part, date); BigQuery's
--    DATE_TRUNC(date, MONTH) takes (date, part) -- reversed argument
--    order. DATE_ADD/DATE_SUB (rather than `date + INTERVAL`) are used
--    for the "last day of month" computation as the more conservatively
--    documented, unambiguously-supported BigQuery date-arithmetic idiom.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.int_calendar_by_store` AS
WITH bounds AS (
    SELECT MIN(date) AS min_date, MAX(date) AS max_date
    FROM `__PROJECT__.__DATASET__.stg_sales`
),
calendar AS (
    SELECT date
    FROM UNNEST(GENERATE_DATE_ARRAY(
        (SELECT min_date FROM bounds), (SELECT max_date FROM bounds), INTERVAL 1 DAY
    )) AS date
),
store_days AS (
    SELECT s.store_nbr, s.city, s.state, c.date
    FROM `__PROJECT__.__DATASET__.stg_stores` s
    CROSS JOIN calendar c
)
SELECT
    sd.store_nbr,
    sd.date,
    COALESCE(MAX(CASE
        WHEN h.locale = 'National' THEN 1
        WHEN h.locale = 'Regional' AND h.locale_name = sd.state THEN 1
        WHEN h.locale = 'Local' AND h.locale_name = sd.city THEN 1
        ELSE 0
    END), 0) = 1 AS is_holiday,
    MAX(h.type) AS holiday_type,
    MAX(h.transferred) AS holiday_transferred,
    MAX(h.description) AS holiday_description,
    EXTRACT(DAYOFWEEK FROM sd.date) - 1 AS day_of_week,
    EXTRACT(DAYOFWEEK FROM sd.date) - 1 IN (0, 6) AS is_weekend,
    (EXTRACT(DAY FROM sd.date) = 15
        OR sd.date = DATE_SUB(DATE_ADD(DATE_TRUNC(sd.date, MONTH), INTERVAL 1 MONTH), INTERVAL 1 DAY)
    ) AS is_payday
FROM store_days sd
LEFT JOIN `__PROJECT__.__DATASET__.stg_holidays_events` h
    ON h.date = sd.date
    AND (
        h.locale = 'National'
        OR (h.locale = 'Regional' AND h.locale_name = sd.state)
        OR (h.locale = 'Local' AND h.locale_name = sd.city)
    )
GROUP BY sd.store_nbr, sd.date;
