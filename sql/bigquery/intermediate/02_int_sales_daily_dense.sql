-- BigQuery port of sql/intermediate/02_int_sales_daily_dense.sql. Same
-- dense hub x SKU x day grid and zero-fill semantics as the DuckDB
-- version (see that file's header comment for the full rationale,
-- unchanged here).
--
-- The one genuine dialect difference: DuckDB lets UNNEST(generate_series(
-- aw.first_sale_date, aw.last_sale_date, ...)) appear directly in a SELECT
-- list, generating a *different* date array per row of active_windows.
-- BigQuery expresses that same "per-row, correlated array expansion" with
-- a comma cross join to UNNEST(GENERATE_DATE_ARRAY(...)) in the FROM
-- clause, referencing the preceding FROM item's columns (aw.first_sale_date /
-- aw.last_sale_date) -- standard, well-documented BigQuery syntax for a
-- lateral/correlated unnest, not a workaround.
--
-- PARTITION BY date CLUSTER BY store_nbr, item_nbr: same grain and scale
-- as stg_sales and fct_sales_daily -- see sql/bigquery/marts/04_fct_sales_daily.sql
-- for the cost reasoning.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.int_sales_daily_dense`
PARTITION BY date
CLUSTER BY store_nbr, item_nbr
AS
WITH active_windows AS (
    SELECT store_nbr, item_nbr, MIN(date) AS first_sale_date, MAX(date) AS last_sale_date
    FROM `__PROJECT__.__DATASET__.stg_sales`
    GROUP BY store_nbr, item_nbr
),
dense_grid AS (
    SELECT
        aw.store_nbr,
        aw.item_nbr,
        date
    FROM active_windows aw,
    UNNEST(GENERATE_DATE_ARRAY(aw.first_sale_date, aw.last_sale_date, INTERVAL 1 DAY)) AS date
)
SELECT
    g.store_nbr, g.item_nbr, g.date,
    COALESCE(s.unit_sales, 0) AS unit_sales,
    s.date IS NULL AS is_imputed_zero,
    COALESCE(s.onpromotion, FALSE) AS onpromotion_filled,
    s.onpromotion IS NULL AS is_promotion_unknown,
    COALESCE(s.is_return, FALSE) AS is_return,
    COALESCE(s.is_fractional_unit, FALSE) AS is_fractional_unit,
    COALESCE(s.was_duplicate_key, FALSE) AS was_duplicate_key,
    COALESCE(s.was_conflicting_duplicate, FALSE) AS was_conflicting_duplicate,
    COALESCE(s.has_unknown_item, FALSE) AS has_unknown_item,
    COALESCE(s.has_unknown_store, FALSE) AS has_unknown_store,
    COALESCE(s.is_extreme_value, FALSE) AS is_extreme_value
FROM dense_grid g
LEFT JOIN `__PROJECT__.__DATASET__.stg_sales` s
    ON s.store_nbr = g.store_nbr AND s.item_nbr = g.item_nbr AND s.date = g.date;
