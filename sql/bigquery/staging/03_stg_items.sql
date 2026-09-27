-- BigQuery port of sql/staging/03_stg_items.sql. Identical logic to the
-- DuckDB version -- typed pass-through of the full (never scoped down)
-- item catalog.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_items` AS
SELECT
    item_nbr,
    family,
    class AS item_class,
    perishable
FROM `__PROJECT__.__DATASET__.raw_items`;
