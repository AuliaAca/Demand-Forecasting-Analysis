-- "Hub" is a simulation proxy for "store" (ADR 0001 A1) -- this dataset has
-- no real fulfillment-hub concept; supermarkets stand in for it. Every store
-- is included; the development scope only restricts the sales fact table.
CREATE OR REPLACE TABLE dim_hub AS
SELECT store_nbr, city, state, store_type, cluster
FROM stg_stores;
