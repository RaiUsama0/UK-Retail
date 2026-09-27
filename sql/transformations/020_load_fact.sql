-- Populates fact_sales from staging + the now-populated dimensions. Must run after
-- 010_load_dimensions.sql. Idempotent via ON CONFLICT (source_row_id) DO UPDATE — this
-- is the pipeline's sole idempotency mechanism for the fact table: source_row_id is a
-- deterministic technical identifier (Phase 3, reused directly here, not duplicated as
-- a second surrogate key), stable across runs as long as the checksum-verified raw
-- file is unchanged. Re-running with identical source data is a true no-op upsert.
--
-- date_key is recomputed here (not joined from dim_date) since it's a deterministic
-- function of invoice_date; the foreign key constraint enforces that the corresponding
-- dim_date row actually exists, which 010_load_dimensions.sql guarantees.

INSERT INTO warehouse.fact_sales (
    source_row_id, invoice_no, product_key, customer_key, country_key, date_key,
    invoice_timestamp, quantity, unit_price, line_revenue, transaction_status,
    flag_missing_customer_id, flag_missing_description, flag_non_positive_price,
    flag_zero_quantity, flag_duplicate_candidate, flag_non_standard_invoice_format,
    flag_non_standard_stock_code
)
SELECT
    s.source_row_id,
    s.invoice_no,
    p.product_key,
    c.customer_key,
    co.country_key,
    TO_CHAR(s.invoice_date, 'YYYYMMDD')::INTEGER,
    s.invoice_date,
    s.quantity,
    s.unit_price,
    s.line_revenue,
    s.transaction_status::warehouse.transaction_status_enum,
    s.flag_missing_customer_id,
    s.flag_missing_description,
    s.flag_non_positive_price,
    s.flag_zero_quantity,
    s.flag_duplicate_candidate,
    s.flag_non_standard_invoice_format,
    s.flag_non_standard_stock_code
FROM staging.stg_cleaned_sales s
JOIN warehouse.dim_product p ON p.stock_code = s.stock_code
LEFT JOIN warehouse.dim_customer c ON c.customer_id = s.customer_id
JOIN warehouse.dim_country co ON co.country_name = s.country
ON CONFLICT (source_row_id) DO UPDATE SET
    invoice_no = EXCLUDED.invoice_no,
    product_key = EXCLUDED.product_key,
    customer_key = EXCLUDED.customer_key,
    country_key = EXCLUDED.country_key,
    date_key = EXCLUDED.date_key,
    invoice_timestamp = EXCLUDED.invoice_timestamp,
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    line_revenue = EXCLUDED.line_revenue,
    transaction_status = EXCLUDED.transaction_status,
    flag_missing_customer_id = EXCLUDED.flag_missing_customer_id,
    flag_missing_description = EXCLUDED.flag_missing_description,
    flag_non_positive_price = EXCLUDED.flag_non_positive_price,
    flag_zero_quantity = EXCLUDED.flag_zero_quantity,
    flag_duplicate_candidate = EXCLUDED.flag_duplicate_candidate,
    flag_non_standard_invoice_format = EXCLUDED.flag_non_standard_invoice_format,
    flag_non_standard_stock_code = EXCLUDED.flag_non_standard_stock_code;
