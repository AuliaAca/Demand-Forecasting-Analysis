CREATE OR REPLACE TABLE stg_oil AS
SELECT
    date,
    dcoilwtico AS oil_price
FROM raw_oil;
