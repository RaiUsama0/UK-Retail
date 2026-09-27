-- Analytical views over the complete fact_sales table. None of these remove rows from
-- the underlying table; they are read-only perspectives. `CREATE OR REPLACE VIEW` is
-- idempotent by nature, so this file is safe to re-run on every pipeline start.

-- 1-4: row-level filtered views, one per transaction_status.
CREATE OR REPLACE VIEW warehouse.v_valid_sales AS
SELECT *
FROM warehouse.fact_sales
WHERE transaction_status = 'valid_sale';

CREATE OR REPLACE VIEW warehouse.v_cancellations AS
SELECT *
FROM warehouse.fact_sales
WHERE transaction_status = 'cancellation';

CREATE OR REPLACE VIEW warehouse.v_potential_returns AS
SELECT *
FROM warehouse.fact_sales
WHERE transaction_status = 'potential_return';

-- Non-standard transactions must never silently enter ordinary sales KPIs; this view
-- surfaces flag_non_standard_invoice_format explicitly so the 3 anomalous "Adjust bad
-- debt"-style rows (see docs/data_dictionary.md) stay identifiable even within it.
CREATE OR REPLACE VIEW warehouse.v_non_standard_transactions AS
SELECT *
FROM warehouse.fact_sales
WHERE transaction_status = 'non_standard';

-- 5: customer-level summary, valid sales only (a cancellation/return doesn't count as
-- a customer "having ordered"; see docs/kpi_definitions.md for the same convention
-- used in the equivalent Python/pandas KPI calculations).
CREATE OR REPLACE VIEW warehouse.v_customer_summary AS
SELECT
    c.customer_key,
    c.customer_id,
    COUNT(DISTINCT f.invoice_no)                       AS order_count,
    SUM(f.line_revenue)                                AS total_net_revenue,
    MIN(f.invoice_timestamp)                           AS first_order_at,
    MAX(f.invoice_timestamp)                           AS last_order_at,
    COUNT(DISTINCT f.invoice_no) > 1                   AS is_repeat_customer
FROM warehouse.dim_customer c
JOIN warehouse.fact_sales f ON f.customer_key = c.customer_key
WHERE f.transaction_status = 'valid_sale'
GROUP BY c.customer_key, c.customer_id;

-- 6: product-level summary, valid sales only.
CREATE OR REPLACE VIEW warehouse.v_product_summary AS
SELECT
    p.product_key,
    p.stock_code,
    p.description,
    COUNT(DISTINCT f.invoice_no)  AS order_count,
    SUM(f.quantity)               AS total_units_sold,
    SUM(f.line_revenue)           AS total_revenue
FROM warehouse.dim_product p
JOIN warehouse.fact_sales f ON f.product_key = p.product_key
WHERE f.transaction_status = 'valid_sale'
GROUP BY p.product_key, p.stock_code, p.description;

-- 7: monthly revenue, using the documented net-revenue formula (valid_sale + cancellation).
CREATE OR REPLACE VIEW warehouse.v_monthly_revenue AS
SELECT
    d.year,
    d.month,
    MIN(d.date_value)                                                      AS month_start,
    SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale')  AS gross_sales_revenue,
    SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation') AS cancellation_value,
    COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale'), 0)
        + COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation'), 0)
                                                                            AS net_revenue,
    COUNT(DISTINCT f.invoice_no) FILTER (WHERE f.transaction_status = 'valid_sale')
                                                                            AS order_count
FROM warehouse.fact_sales f
JOIN warehouse.dim_date d ON d.date_key = f.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- 8: data quality monitoring — a live-queryable equivalent of reports/cleaning_summary.json.
CREATE OR REPLACE VIEW warehouse.v_data_quality_monitor AS
SELECT
    transaction_status,
    COUNT(*)                                              AS row_count,
    COUNT(*) FILTER (WHERE flag_missing_customer_id)      AS missing_customer_id_count,
    COUNT(*) FILTER (WHERE flag_missing_description)      AS missing_description_count,
    COUNT(*) FILTER (WHERE flag_non_positive_price)       AS non_positive_price_count,
    COUNT(*) FILTER (WHERE flag_zero_quantity)            AS zero_quantity_count,
    COUNT(*) FILTER (WHERE flag_duplicate_candidate)      AS duplicate_candidate_count,
    COUNT(*) FILTER (WHERE flag_non_standard_invoice_format) AS non_standard_invoice_format_count,
    COUNT(*) FILTER (WHERE flag_non_standard_stock_code)  AS non_standard_stock_code_count
FROM warehouse.fact_sales
GROUP BY transaction_status;

-- Optional deduplicated variant of v_valid_sales.
--
-- Selection rule: within each exact-duplicate group (flag_duplicate_candidate = true),
-- keep only the row with the lowest source_row_id (the first occurrence in the raw
-- file); every other row in that group is dropped. Non-duplicate rows are unaffected.
--
-- Suitable for: a conservative revenue estimate when double-scanned line items are
-- suspected to inflate totals.
-- NOT suitable for: any analysis where a genuine repeat purchase of the same
-- product/quantity/price in the same session is plausible (e.g. wholesale reseller
-- customers in this dataset) — this rule cannot distinguish a duplicate scan from a
-- real repeat line, so it necessarily discards some real transactions along with the
-- scanning errors. Use v_valid_sales (the complete table) unless this trade-off is
-- specifically what the analysis calls for.
CREATE OR REPLACE VIEW warehouse.v_valid_sales_deduplicated AS
SELECT *
FROM (
    SELECT
        f.*,
        ROW_NUMBER() OVER (
            PARTITION BY f.invoice_no, f.product_key, f.customer_key, f.country_key,
                         f.invoice_timestamp, f.quantity, f.unit_price
            ORDER BY f.source_row_id
        ) AS dedup_rank
    FROM warehouse.fact_sales f
    WHERE f.transaction_status = 'valid_sale'
) ranked
WHERE dedup_rank = 1;
