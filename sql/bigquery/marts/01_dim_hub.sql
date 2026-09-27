-- BigQuery port of sql/marts/01_dim_hub.sql. Identical logic to the
-- DuckDB version. No PARTITION BY / CLUSTER BY: this dimension table is
-- small (tens of stores), far below the scale where partitioning or
-- clustering reduces bytes scanned -- adding either here would be exactly
-- the "infrastructure for appearance" CLAUDE.md Section 18 warns against.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.dim_hub` AS
SELECT store_nbr, city, state, store_type, cluster
FROM `__PROJECT__.__DATASET__.stg_stores`;
