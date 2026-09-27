-- Loads the frozen, reproducible item selection from Phase 01
-- (docs/decisions/0001-phase00-decisions-and-scope.md, Section 2) as a
-- queryable table. This is a small list of item IDs and their strata, not
-- raw sales data -- see that ADR for the sampling methodology.
CREATE OR REPLACE TABLE stg_dev_scope_items AS
SELECT * FROM read_csv_auto('__DEV_SCOPE_ITEMS_CSV__', SAMPLE_SIZE=-1);
