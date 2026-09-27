-- Typed, renamed pass-through. Every store is kept -- ADR 0001 Section 2.1
-- keeps the full hub/store breadth; only the item dimension is scoped down.
CREATE OR REPLACE TABLE stg_stores AS
SELECT
    store_nbr,
    city,
    state,
    type AS store_type,
    cluster
FROM raw_stores;
