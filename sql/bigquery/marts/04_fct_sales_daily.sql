-- BigQuery port of sql/marts/04_fct_sales_daily.sql -- same "materialized
-- copy of int_sales_daily_dense" shape as the DuckDB version, and the one
-- place in this whole port where the partition/cluster choice actually
-- matters (see docs/phase_reports/phase13.md for the worked bytes-scanned
-- cost example).
--
-- PARTITION BY date: every query this project's forecasting/evaluation
-- code issues against this table is date-scoped (an as-of cutoff, a
-- target-date range, a holdout window). Partitioning lets BigQuery prune
-- whole partitions outside that range instead of scanning the full table
-- -- the single biggest lever on cost for a table at this grain (hub x
-- SKU x day). At real scale (~4.6 years, under 1,700 calendar days) this
-- comfortably stays under BigQuery's 4,000-partitions-per-table default
-- limit for a date-partitioned table.
--
-- CLUSTER BY store_nbr, item_nbr: within a date partition, this is the
-- exact grain most downstream queries filter or join on (a specific hub x
-- SKU series' history). Clustering sorts storage blocks by these columns
-- so a filtered query also skips blocks it doesn't need within the
-- partitions it does scan.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.fct_sales_daily`
PARTITION BY date
CLUSTER BY store_nbr, item_nbr
AS
SELECT * FROM `__PROJECT__.__DATASET__.int_sales_daily_dense`;
