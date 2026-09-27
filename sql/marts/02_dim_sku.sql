-- The FULL item catalog, never scoped down -- only the sales fact table
-- (fct_sales_daily) is restricted to the controlled development scope, so
-- this dimension stays a complete, trustworthy reference table.
-- is_in_dev_scope and the stratification attributes let a query filter to
-- the development scope explicitly when it needs to, without truncating
-- the dimension itself.
CREATE OR REPLACE TABLE dim_sku AS
SELECT
    i.item_nbr,
    i.family,
    i.item_class,
    i.perishable,
    COALESCE(d.selected, FALSE) AS is_in_dev_scope,
    d.volume_quantile,
    d.promo_flag,
    d.total_unit_sales AS historical_total_unit_sales
FROM stg_items i
LEFT JOIN stg_dev_scope_items d ON d.item_nbr = i.item_nbr;
