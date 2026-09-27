-- stg_sales: one row per (date, store_nbr, item_nbr), restricted to the
-- controlled development scope (ADR 0001 Section 2), with Phase 02's
-- data-quality handling decisions actually applied here for the first time:
--
--   R1 grain_duplicates      -- keep exactly one row per key (the row with
--                                the highest id wins on conflict);
--                                was_duplicate_key / was_conflicting_duplicate
--                                record what happened -- evidence is never
--                                thrown away, only the extra row is dropped.
--   R2 null_keys              -- a row with any null key never reaches this
--                                table at all (see 08_stg_sales_rejected_null_keys.sql).
--   R3 orphan_dimension_keys -- kept and flagged (has_unknown_item /
--                                has_unknown_store), never dropped --
--                                including when the item isn't even in the
--                                dev-scope catalog: an orphan item can't be
--                                "in scope" or "out of scope" (it isn't a
--                                recognized SKU at all), so it is explicitly
--                                let through the scope filter below rather
--                                than silently disappearing because it
--                                failed an "IN (known, selected items)" test.
--   R5 suspicious_negative_values -- kept and flagged (is_return).
--   R6 suspicious_extreme_values  -- kept and flagged (is_extreme_value),
--                                using a fence fit on the FULL raw table's
--                                distribution, not just the dev-scope
--                                sample -- a ~10% item sample would make the
--                                fence noisier and would drift every time
--                                the sample is redrawn (see
--                                docs/phase_reports/phase03.md). The 3.0
--                                multiplier here must match
--                                demandflow.quality.rules.EXTREME_VALUE_IQR_MULTIPLIER
--                                (pinned by a test).
--   R7 onpromotion_missing   -- NULL kept as a distinct state
--                                (is_promotion_unknown), never coerced to FALSE.

CREATE OR REPLACE TABLE stg_sales AS
WITH scoped_raw AS (
    SELECT *
    FROM raw_train
    WHERE date IS NOT NULL AND store_nbr IS NOT NULL AND item_nbr IS NOT NULL
      AND (
            item_nbr IN (SELECT item_nbr FROM stg_dev_scope_items WHERE selected)
            OR item_nbr NOT IN (SELECT item_nbr FROM raw_items WHERE item_nbr IS NOT NULL)
          )
),
keyed AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY date, store_nbr, item_nbr ORDER BY id DESC) AS rn_desc,
        COUNT(*) OVER (PARTITION BY date, store_nbr, item_nbr) AS key_row_count,
        COUNT(DISTINCT unit_sales) OVER (PARTITION BY date, store_nbr, item_nbr) AS distinct_unit_sales_in_key,
        COUNT(DISTINCT COALESCE(CAST(onpromotion AS VARCHAR), 'NULL'))
            OVER (PARTITION BY date, store_nbr, item_nbr) AS distinct_onpromotion_in_key
    FROM scoped_raw
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
    SELECT
        QUANTILE_CONT(unit_sales, 0.75) AS q3,
        QUANTILE_CONT(unit_sales, 0.75) - QUANTILE_CONT(unit_sales, 0.25) AS iqr
    FROM raw_train
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
    NOT EXISTS (SELECT 1 FROM raw_items i WHERE i.item_nbr = d.item_nbr) AS has_unknown_item,
    NOT EXISTS (SELECT 1 FROM raw_stores s WHERE s.store_nbr = d.store_nbr) AS has_unknown_store,
    d.unit_sales > (f.q3 + 3.0 * f.iqr) AS is_extreme_value
FROM deduped d
CROSS JOIN extreme_fence f;
