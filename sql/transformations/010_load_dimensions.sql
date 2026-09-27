-- Populates every dimension from the current contents of staging.stg_cleaned_sales.
-- Idempotent: safe to run every pipeline load. Must run before 020_load_fact.sql
-- (fact_sales' foreign keys require every dimension row to already exist).

-- dim_date: one row per calendar day spanning the observed invoice_date range (not
-- just days that had a transaction) — standard calendar-dimension practice.
INSERT INTO warehouse.dim_date (
    date_key, date_value, year, quarter, month, month_name, day, day_of_week, day_name, is_weekend
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER,
    d,
    EXTRACT(YEAR FROM d)::SMALLINT,
    EXTRACT(QUARTER FROM d)::SMALLINT,
    EXTRACT(MONTH FROM d)::SMALLINT,
    TRIM(TO_CHAR(d, 'Month')),
    EXTRACT(DAY FROM d)::SMALLINT,
    (EXTRACT(ISODOW FROM d)::SMALLINT - 1),  -- ISODOW 1=Mon..7=Sun -> shifted to 0=Mon..6=Sun
    TRIM(TO_CHAR(d, 'Day')),
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(
    (SELECT MIN(invoice_date)::date FROM staging.stg_cleaned_sales),
    (SELECT MAX(invoice_date)::date FROM staging.stg_cleaned_sales),
    interval '1 day'
) AS d
ON CONFLICT (date_key) DO NOTHING;

-- dim_country
INSERT INTO warehouse.dim_country (country_name)
SELECT DISTINCT country
FROM staging.stg_cleaned_sales
ON CONFLICT (country_name) DO NOTHING;

-- dim_customer: never invents a customer for a missing CustomerID.
INSERT INTO warehouse.dim_customer (customer_id)
SELECT DISTINCT customer_id
FROM staging.stg_cleaned_sales
WHERE customer_id IS NOT NULL
ON CONFLICT (customer_id) DO NOTHING;

-- dim_product: description is the MODE (most frequent non-null value) of that stock
-- code's observed descriptions — not assumed unique. description_variant_count records
-- how many distinct non-null descriptions were actually observed (647 stock codes have
-- more than 1 in the real dataset; see docs/data_dictionary.md).
INSERT INTO warehouse.dim_product (stock_code, description, description_variant_count)
SELECT
    stock_code,
    MODE() WITHIN GROUP (ORDER BY description) FILTER (WHERE description IS NOT NULL),
    COUNT(DISTINCT description) FILTER (WHERE description IS NOT NULL)
FROM staging.stg_cleaned_sales
GROUP BY stock_code
ON CONFLICT (stock_code) DO UPDATE SET
    description = EXCLUDED.description,
    description_variant_count = EXCLUDED.description_variant_count;
