-- Section D: TRANSACTION QUALITY

-- D1. Transaction status distribution — row count and share, plus the associated
-- revenue value per status (reusing warehouse.v_data_quality_monitor's grouping but
-- adding revenue, which that view does not include).
SELECT
    transaction_status,
    COUNT(*) AS row_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_rows,
    SUM(line_revenue) AS total_line_revenue
FROM warehouse.fact_sales
GROUP BY transaction_status
ORDER BY row_count DESC;

-- D2. Cancellation frequency and potential-return frequency, computed independently
-- so cancellation revenue is never double-counted against potential-return revenue
-- (the two are mutually exclusive transaction_status values by construction — see
-- cleaning.classify_transactions's precedence rule).
SELECT
    (SELECT COUNT(*) FROM warehouse.fact_sales WHERE transaction_status = 'cancellation')
        AS cancellation_row_count,
    (SELECT SUM(line_revenue) FROM warehouse.fact_sales WHERE transaction_status = 'cancellation')
        AS cancellation_value,
    (SELECT COUNT(*) FROM warehouse.fact_sales WHERE transaction_status = 'potential_return')
        AS potential_return_row_count,
    (SELECT SUM(line_revenue) FROM warehouse.fact_sales WHERE transaction_status = 'potential_return')
        AS potential_return_value;

-- D3. Non-standard transaction counts, broken down by contributing flag (a row can
-- match more than one reason simultaneously — counts will not sum to the total).
SELECT
    COUNT(*) AS total_non_standard,
    COUNT(*) FILTER (WHERE flag_non_positive_price) AS non_positive_price_count,
    COUNT(*) FILTER (WHERE flag_zero_quantity) AS zero_quantity_count,
    COUNT(*) FILTER (WHERE flag_non_standard_invoice_format) AS non_standard_invoice_format_count
FROM warehouse.fact_sales
WHERE transaction_status = 'non_standard';

-- D4. Missing customer identifier rate, overall and split by transaction_status.
SELECT
    transaction_status,
    COUNT(*) AS row_count,
    COUNT(*) FILTER (WHERE flag_missing_customer_id) AS missing_customer_id_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE flag_missing_customer_id) / COUNT(*), 2)
        AS missing_customer_id_pct
FROM warehouse.fact_sales
GROUP BY transaction_status
ORDER BY transaction_status;

-- D5. Duplicate-candidate frequency, overall and by status.
SELECT
    transaction_status,
    COUNT(*) AS row_count,
    COUNT(*) FILTER (WHERE flag_duplicate_candidate) AS duplicate_candidate_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE flag_duplicate_candidate) / COUNT(*), 2)
        AS duplicate_candidate_pct
FROM warehouse.fact_sales
GROUP BY transaction_status
ORDER BY transaction_status;

-- D6. Revenue sensitivity to duplicate handling — complete dataset vs. the documented
-- deduplicated view (see warehouse.v_valid_sales_deduplicated's comment for the exact
-- selection rule and its limitations before interpreting this delta).
SELECT * FROM warehouse.v_duplicate_sensitivity;
SELECT * FROM warehouse.v_duplicate_sensitivity_delta;

-- D7. The three anomalous-invoice-format rows, shown explicitly with their full
-- context, so they are never silently absorbed into an aggregate without a human
-- being able to see exactly what they are.
SELECT source_row_id, invoice_no, quantity, unit_price, line_revenue, transaction_status
FROM warehouse.fact_sales
WHERE flag_non_standard_invoice_format
ORDER BY source_row_id;
