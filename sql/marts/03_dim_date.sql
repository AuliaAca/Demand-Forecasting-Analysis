-- A standard date dimension spanning stg_sales' observed date range.
CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM stg_sales
),
calendar AS (
    SELECT CAST(UNNEST(generate_series(
        (SELECT min_date FROM bounds), (SELECT max_date FROM bounds), INTERVAL 1 DAY
    )) AS DATE) AS date
)
SELECT
    date,
    EXTRACT(year FROM date) AS year,
    EXTRACT(month FROM date) AS month,
    EXTRACT(day FROM date) AS day_of_month,
    EXTRACT(dow FROM date) AS day_of_week,
    EXTRACT(dow FROM date) IN (0, 6) AS is_weekend,
    EXTRACT(week FROM date) AS iso_week,
    strftime(date, '%B') AS month_name,
    (EXTRACT(day FROM date) = 15
        OR date = (date_trunc('month', date) + INTERVAL 1 MONTH - INTERVAL 1 DAY)) AS is_payday
FROM calendar;
