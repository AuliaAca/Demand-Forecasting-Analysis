-- BigQuery port of sql/marts/02_dim_sku.sql. Identical logic to the
-- DuckDB version. No PARTITION BY / CLUSTER BY -- same reasoning as
-- dim_hub.sql: this dimension table (thousands of items at most) is too
-- small for partitioning/clustering to meaningfully reduce cost.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.dim_sku` AS
SELECT
    i.item_nbr,
    i.family,
    i.item_class,
    i.perishable,
    COALESCE(d.selected, FALSE) AS is_in_dev_scope,
    d.volume_quantile,
    d.promo_flag,
    d.total_unit_sales AS historical_total_unit_sales
FROM `__PROJECT__.__DATASET__.stg_items` i
LEFT JOIN `__PROJECT__.__DATASET__.stg_dev_scope_items` d ON d.item_nbr = i.item_nbr;
