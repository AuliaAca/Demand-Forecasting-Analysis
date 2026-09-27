-- BigQuery port of sql/staging/07_stg_sales.sql. Same Phase 02 data-quality
-- handling decisions as the DuckDB version (R1 grain_duplicates, R2
-- null_keys, R3 orphan_dimension_keys, R5 suspicious_negative_values, R6
-- suspicious_extreme_values, R7 onpromotion_missing -- see that file's
-- header comment for the full rule-by-rule rationale, unchanged here) --
-- restructured in two places where DuckDB and BigQuery genuinely diverge,
-- not just re-typed:
--
-- 1. DuckDB freely supports COUNT(DISTINCT x) OVER (PARTITION BY ...).
--    BigQuery's analytic (window) functions do not reliably support the
--    DISTINCT keyword the same way, so `key_stats` computes the same
--    per-key duplicate/conflict counts with an ordinary GROUP BY, then
--    JOINs them back onto the row-level data -- a portable, unambiguous
--    equivalent, not an approximation.
-- 2. DuckDB's QUANTILE_CONT(x, p) aggregate becomes BigQuery's
--    PERCENTILE_CONT(x, p) OVER () analytic function -- both are the
--    exact, continuous (interpolated) percentile, not APPROX_QUANTILES'
--    approximation, which would risk silently shifting the extreme-value
--    fence away from the 3.0x-IQR value
--    demandflow.quality.rules.EXTREME_VALUE_IQR_MULTIPLIER is pinned to.
--
-- PARTITION BY date CLUSTER BY store_nbr, item_nbr: this table is at the
-- same grain and scale as fct_sales_daily (the one place in this project
-- large enough for partitioning/clustering to actually reduce bytes
-- scanned -- see sql/bigquery/marts/04_fct_sales_daily.sql and
-- docs/phase_reports/phase13.md for the cost reasoning) and is itself
-- scanned again to build int_sales_daily_dense downstream.
CREATE OR REPLACE TABLE `__PROJECT__.__DATASET__.stg_sales`
PARTITION BY date
CLUSTER BY store_nbr, item_nbr
AS
WITH scoped_raw AS (
    SELECT *
    FROM `__PROJECT__.__DATASET__.raw_train`
    WHERE date IS NOT NULL AND store_nbr IS NOT NULL AND item_nbr IS NOT NULL
      AND (
            item_nbr IN (SELECT item_nbr FROM `__PROJECT__.__DATASET__.stg_dev_scope_items` WHERE selected)
            OR item_nbr NOT IN (SELECT item_nbr FROM `__PROJECT__.__DATASET__.raw_items` WHERE item_nbr IS NOT NULL)
          )
),
key_stats AS (
    SELECT
        date, store_nbr, item_nbr,
        COUNT(*) AS key_row_count,
        COUNT(DISTINCT unit_sales) AS distinct_unit_sales_in_key,
        COUNT(DISTINCT COALESCE(CAST(onpromotion AS STRING), 'NULL')) AS distinct_onpromotion_in_key
    FROM scoped_raw
    GROUP BY date, store_nbr, item_nbr
),
keyed AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (PARTITION BY r.date, r.store_nbr, r.item_nbr ORDER BY r.id DESC) AS rn_desc,
        k.key_row_count,
        k.distinct_unit_sales_in_key,
        k.distinct_onpromotion_in_key
    FROM scoped_raw r
    JOIN key_stats k
        ON k.date = r.date AND k.store_nbr = r.store_nbr AND k.item_nbr = r.item_nbr
),
deduped AS (
    SELECT
        id, date, store_nbr, item_nbr, unit_sales, onpromotion,
        key_row_count > 1 AS was_duplicate_key,
        key_row_count > 1
            AND (distinct_unit_sales_in_key > 1 OR distinct_onpromotion_in_key > 1) AS was_conflicting_duplicate
    FROM keyed
    WHERE rn_desc = 1
),
extreme_fence AS (
    SELECT DISTINCT
        PERCENTILE_CONT(unit_sales, 0.75) OVER () AS q3,
        PERCENTILE_CONT(unit_sales, 0.75) OVER () - PERCENTILE_CONT(unit_sales, 0.25) OVER () AS iqr
    FROM `__PROJECT__.__DATASET__.raw_train`
    WHERE unit_sales > 0
)
SELECT
    d.id,
    d.date,
    d.store_nbr,
    d.item_nbr,
    d.unit_sales,
    d.onpromotion,
    d.was_duplicate_key,
    d.was_conflicting_duplicate,
    d.unit_sales < 0 AS is_return,
    d.unit_sales <> FLOOR(d.unit_sales) AS is_fractional_unit,
    d.onpromotion IS NULL AS is_promotion_unknown,
    NOT EXISTS (SELECT 1 FROM `__PROJECT__.__DATASET__.raw_items` i WHERE i.item_nbr = d.item_nbr) AS has_unknown_item,
    NOT EXISTS (SELECT 1 FROM `__PROJECT__.__DATASET__.raw_stores` s WHERE s.store_nbr = d.store_nbr) AS has_unknown_store,
    d.unit_sales > (f.q3 + 3.0 * f.iqr) AS is_extreme_value
FROM deduped d
CROSS JOIN extreme_fence f;
