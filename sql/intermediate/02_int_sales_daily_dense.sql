-- Dense hub x SKU x day grid: one row per day in each (store_nbr, item_nbr)
-- pair's *active window* -- from its first observed sale to its last
-- (Phase 00 assumption A3). A day inside that window with no matching row
-- in stg_sales means zero RECORDED sales, flagged via is_imputed_zero; it
-- does NOT mean zero demand -- this dataset carries no stockout signal (see
-- the dataset card's "Known limitations"), so the data cannot distinguish
-- "genuinely no demand" from "recorded incorrectly" or "out of stock".
--
-- Days outside every pair's own active window are not included at all --
-- there is no reasonable inference to make about an item before its first
-- sale or after its last (Phase 00 risk K4).
--
-- [LIMITATION] has_unknown_item / has_unknown_store / was_duplicate_key /
-- was_conflicting_duplicate / is_return / is_fractional_unit / is_extreme_value
-- all describe a specific OBSERVED row in stg_sales. An imputed day within
-- an orphan item's active window does not inherit has_unknown_item -- these
-- flags describe row provenance, not a blanket property of the item.

CREATE OR REPLACE TABLE int_sales_daily_dense AS
WITH active_windows AS (
    SELECT store_nbr, item_nbr, MIN(date) AS first_sale_date, MAX(date) AS last_sale_date
    FROM stg_sales
    GROUP BY store_nbr, item_nbr
),
dense_grid AS (
    SELECT
        aw.store_nbr,
        aw.item_nbr,
        CAST(UNNEST(generate_series(
            aw.first_sale_date, aw.last_sale_date, INTERVAL 1 DAY
        )) AS DATE) AS date
    FROM active_windows aw
)
SELECT
    g.store_nbr,
    g.item_nbr,
    g.date,
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
LEFT JOIN stg_sales s
    ON s.store_nbr = g.store_nbr AND s.item_nbr = g.item_nbr AND s.date = g.date;
