-- R2 null_keys handling decision (Phase 02): never load a null-key row into
-- stg_sales; keep it here instead, inspectable, per CLAUDE.md Section 12's
-- "do not silently remove problematic records" rule. Not scoped by dev-scope
-- item selection -- a row missing its own key cannot be meaningfully tested
-- for scope membership in the first place.
CREATE OR REPLACE TABLE stg_sales_rejected_null_keys AS
SELECT *, 'null_key' AS reject_reason
FROM raw_train
WHERE date IS NULL OR store_nbr IS NULL OR item_nbr IS NULL;
