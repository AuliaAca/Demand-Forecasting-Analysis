CREATE OR REPLACE TABLE stg_transactions AS
SELECT
    date,
    store_nbr,
    transactions AS transaction_count
FROM raw_transactions;
