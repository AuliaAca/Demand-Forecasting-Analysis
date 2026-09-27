-- Typed, renamed pass-through of the FULL item catalog (never scoped down --
-- see dim_sku.sql for why the dimension table stays complete while only the
-- sales fact table is restricted to the development scope).
CREATE OR REPLACE TABLE stg_items AS
SELECT
    item_nbr,
    family,
    class AS item_class,
    perishable
FROM raw_items;
