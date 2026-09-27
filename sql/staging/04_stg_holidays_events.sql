CREATE OR REPLACE TABLE stg_holidays_events AS
SELECT
    date,
    type,
    locale,
    locale_name,
    description,
    transferred
FROM raw_holidays_events;
