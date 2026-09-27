-- A store x day calendar spanning stg_sales' observed date range, with
-- national/regional/local holidays resolved per store's city/state (the
-- JD's "seasonal events" dimension) and an approximate payday flag.
--
-- [DECISION] Payday = the 15th or the last day of the month, per the
-- Phase 00 public-documentation research on this dataset (Ecuadorian
-- public-sector pay dates) -- not a value present in the raw data.
--
-- [LIMITATION] A "transferred" holiday is passed through as a flag
-- (holiday_transferred) but not fully re-resolved to its actual observed
-- date; see docs/phase_reports/phase03.md for why this is deferred rather
-- than silently assumed correct.

CREATE OR REPLACE TABLE int_calendar_by_store AS
WITH bounds AS (
    SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM stg_sales
),
calendar AS (
    SELECT CAST(UNNEST(generate_series(
        (SELECT min_date FROM bounds), (SELECT max_date FROM bounds), INTERVAL 1 DAY
    )) AS DATE) AS date
),
store_days AS (
    SELECT s.store_nbr, s.city, s.state, c.date
    FROM stg_stores s
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
    EXTRACT(dow FROM sd.date) AS day_of_week,
    EXTRACT(dow FROM sd.date) IN (0, 6) AS is_weekend,
    (EXTRACT(day FROM sd.date) = 15
        OR sd.date = (date_trunc('month', sd.date) + INTERVAL 1 MONTH - INTERVAL 1 DAY)) AS is_payday
FROM store_days sd
LEFT JOIN stg_holidays_events h
    ON h.date = sd.date
    AND (
        h.locale = 'National'
        OR (h.locale = 'Regional' AND h.locale_name = sd.state)
        OR (h.locale = 'Local' AND h.locale_name = sd.city)
    )
GROUP BY sd.store_nbr, sd.date;
