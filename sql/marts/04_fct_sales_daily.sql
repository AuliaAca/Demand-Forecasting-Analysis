-- The primary sales fact, at hub x SKU x day grain. A materialized copy of
-- int_sales_daily_dense: intermediate vs. mart here is a pipeline-
-- organization distinction (working table vs. the documented, serving
-- table other phases and consumers query), not a column-reduction step --
-- the DQ flag columns are kept because Phase 04+ genuinely needs them to
-- decide how to treat flagged points, not just for internal debugging.
CREATE OR REPLACE TABLE fct_sales_daily AS
SELECT * FROM int_sales_daily_dense;
