-- Phase 5 analytical views. All read-only, all built on the complete fact_sales table
-- (never a pre-filtered copy) or on v_valid_sales_deduplicated where explicitly named.
-- Idempotent (CREATE OR REPLACE), safe to re-run every pipeline start.

-- =====================================================================================
-- A. SALES PERFORMANCE
-- =====================================================================================

-- Monthly revenue with growth, cumulative total, and a genuinely-derived partial-month
-- flag (not assumed). A month is "partial" only if it is the dataset's very first or
-- very last calendar month AND the dataset's actual min/max date doesn't reach that
-- month's calendar boundary. Verified against the real data: the dataset starts
-- exactly on 2010-12-01 (the 1st) so December 2010 is NOT partial by this rule, even
-- though its last recorded sale is the 23rd (a business/holiday gap, not a truncated
-- observation window) — December 2011 IS partial (last recorded sale: the 9th, well
-- short of the 31st, matching the known export cutoff).
CREATE OR REPLACE VIEW warehouse.v_monthly_revenue_growth AS
WITH bounds AS (
    SELECT MIN(invoice_timestamp) AS dataset_min_ts, MAX(invoice_timestamp) AS dataset_max_ts
    FROM warehouse.fact_sales
),
monthly AS (
    SELECT
        d.year,
        d.month,
        MIN(d.date_value) AS month_start,
        (DATE_TRUNC('month', MIN(d.date_value)) + INTERVAL '1 month' - INTERVAL '1 day')::date
            AS month_calendar_end,
        SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale') AS gross_sales_revenue,
        SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation') AS cancellation_value,
        COUNT(DISTINCT f.invoice_no) FILTER (WHERE f.transaction_status = 'valid_sale') AS order_count
    FROM warehouse.fact_sales f
    JOIN warehouse.dim_date d ON d.date_key = f.date_key
    GROUP BY d.year, d.month
),
enriched AS (
    SELECT
        m.year,
        m.month,
        m.month_start,
        COALESCE(m.gross_sales_revenue, 0) AS gross_sales_revenue,
        COALESCE(m.cancellation_value, 0) AS cancellation_value,
        COALESCE(m.gross_sales_revenue, 0) + COALESCE(m.cancellation_value, 0) AS net_revenue,
        m.order_count,
        (
            (
                m.year = EXTRACT(YEAR FROM b.dataset_min_ts)::smallint
                AND m.month = EXTRACT(MONTH FROM b.dataset_min_ts)::smallint
                AND b.dataset_min_ts::date > m.month_start
            )
            OR
            (
                m.year = EXTRACT(YEAR FROM b.dataset_max_ts)::smallint
                AND m.month = EXTRACT(MONTH FROM b.dataset_max_ts)::smallint
                AND b.dataset_max_ts::date < m.month_calendar_end
            )
        ) AS is_partial_month
    FROM monthly m
    CROSS JOIN bounds b
)
SELECT
    year,
    month,
    month_start,
    is_partial_month,
    gross_sales_revenue,
    cancellation_value,
    net_revenue,
    order_count,
    CASE WHEN order_count > 0 THEN ROUND(net_revenue / order_count, 2) ELSE NULL END
        AS average_order_value,
    LAG(net_revenue) OVER (ORDER BY year, month) AS previous_month_net_revenue,
    CASE
        WHEN LAG(net_revenue) OVER (ORDER BY year, month) IS NULL THEN NULL
        WHEN LAG(net_revenue) OVER (ORDER BY year, month) = 0 THEN NULL
        ELSE ROUND(
            100.0 * (net_revenue - LAG(net_revenue) OVER (ORDER BY year, month))
                / LAG(net_revenue) OVER (ORDER BY year, month),
            2
        )
    END AS month_over_month_growth_pct,
    SUM(net_revenue) OVER (
        ORDER BY year, month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_net_revenue
FROM enriched
ORDER BY year, month;

-- Revenue by country, ranked. Uses the full fact table (a cancellation still belongs
-- to the country it was cancelled from).
CREATE OR REPLACE VIEW warehouse.v_revenue_by_country AS
SELECT
    co.country_key,
    co.country_name,
    COUNT(DISTINCT f.invoice_no) FILTER (WHERE f.transaction_status = 'valid_sale') AS order_count,
    COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale'), 0)
        AS gross_sales_revenue,
    COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation'), 0)
        AS cancellation_value,
    COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale'), 0)
        + COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation'), 0)
        AS net_revenue,
    RANK() OVER (
        ORDER BY COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale'), 0)
            + COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation'), 0) DESC
    ) AS revenue_rank
FROM warehouse.dim_country co
JOIN warehouse.fact_sales f ON f.country_key = co.country_key
GROUP BY co.country_key, co.country_name;

-- =====================================================================================
-- B. PRODUCT PERFORMANCE
-- =====================================================================================

-- Overall product performance: revenue, units, revenue contribution %, and both
-- rankings (revenue and quantity are not always the same product).
CREATE OR REPLACE VIEW warehouse.v_product_performance AS
WITH product_sales AS (
    SELECT
        p.product_key,
        p.stock_code,
        p.description,
        SUM(f.quantity) AS units_sold,
        SUM(f.line_revenue) AS revenue,
        COUNT(DISTINCT f.invoice_no) AS order_count
    FROM warehouse.dim_product p
    JOIN warehouse.fact_sales f ON f.product_key = p.product_key
    WHERE f.transaction_status = 'valid_sale'
    GROUP BY p.product_key, p.stock_code, p.description
),
totals AS (
    SELECT SUM(revenue) AS total_revenue FROM product_sales
)
SELECT
    ps.product_key,
    ps.stock_code,
    ps.description,
    ps.units_sold,
    ps.revenue,
    ps.order_count,
    RANK() OVER (ORDER BY ps.revenue DESC) AS revenue_rank,
    RANK() OVER (ORDER BY ps.units_sold DESC) AS quantity_rank,
    ROUND(100.0 * ps.revenue / NULLIF(t.total_revenue, 0), 4) AS pct_of_total_revenue
FROM product_sales ps
CROSS JOIN totals t;

-- Product ranking WITHIN each country (a top-UK product need not be a top-France one).
CREATE OR REPLACE VIEW warehouse.v_product_country_rankings AS
SELECT
    co.country_name,
    p.stock_code,
    p.description,
    SUM(f.line_revenue) AS revenue,
    RANK() OVER (PARTITION BY co.country_name ORDER BY SUM(f.line_revenue) DESC)
        AS rank_within_country
FROM warehouse.fact_sales f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
JOIN warehouse.dim_country co ON co.country_key = f.country_key
WHERE f.transaction_status = 'valid_sale'
GROUP BY co.country_name, p.stock_code, p.description;

-- Monthly sales trend per product.
CREATE OR REPLACE VIEW warehouse.v_product_monthly_trend AS
SELECT
    p.stock_code,
    p.description,
    d.year,
    d.month,
    SUM(f.quantity) AS units_sold,
    SUM(f.line_revenue) AS revenue
FROM warehouse.fact_sales f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
JOIN warehouse.dim_date d ON d.date_key = f.date_key
WHERE f.transaction_status = 'valid_sale'
GROUP BY p.stock_code, p.description, d.year, d.month;

-- Products most associated with cancellation activity (only products with at least
-- one cancellation appear).
CREATE OR REPLACE VIEW warehouse.v_product_cancellation_activity AS
SELECT
    p.stock_code,
    p.description,
    COUNT(*) FILTER (WHERE f.transaction_status = 'cancellation') AS cancellation_count,
    SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation') AS cancellation_value,
    COUNT(*) FILTER (WHERE f.transaction_status = 'valid_sale') AS valid_sale_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE f.transaction_status = 'cancellation')
            / NULLIF(
                COUNT(*) FILTER (WHERE f.transaction_status IN ('valid_sale', 'cancellation')), 0
            ),
        2
    ) AS cancellation_rate_pct
FROM warehouse.dim_product p
JOIN warehouse.fact_sales f ON f.product_key = p.product_key
GROUP BY p.stock_code, p.description
HAVING COUNT(*) FILTER (WHERE f.transaction_status = 'cancellation') > 0
ORDER BY cancellation_count DESC;

-- =====================================================================================
-- C. CUSTOMER INTELLIGENCE
-- =====================================================================================

-- RFM segmentation. Reference date is derived from the data (max invoice_timestamp + 1
-- day), NOT wall-clock "today" — reproducible regardless of when this view is queried.
-- Monetary nets a customer's valid_sale revenue against their OWN cancellation value;
-- 383 of 9,288 cancellation rows (4.1%) have no CustomerID and so cannot be attributed
-- to any individual customer here (they are still counted in organisation-wide net
-- revenue — see v_monthly_revenue_growth). Frequency and Recency use valid_sale
-- invoices only: a cancellation alone does not count as a purchase or update recency.
-- Customers with zero qualifying (valid_sale) purchases are excluded entirely — RFM is
-- an identity-dependent, purchase-dependent metric, not applicable to them.
--
-- The rfm_segment_heuristic label is exactly that: a heuristic derived from simple
-- quartile-score thresholds, not a validated behavioural model. Interpret it as a
-- starting point for further investigation, not a proven customer typology.
CREATE OR REPLACE VIEW warehouse.v_customer_rfm AS
WITH reference AS (
    SELECT (MAX(invoice_timestamp) + INTERVAL '1 day')::date AS reference_date
    FROM warehouse.fact_sales
),
customer_txn AS (
    SELECT
        c.customer_key,
        c.customer_id,
        MIN(f.invoice_timestamp) FILTER (WHERE f.transaction_status = 'valid_sale')
            AS first_purchase_at,
        MAX(f.invoice_timestamp) FILTER (WHERE f.transaction_status = 'valid_sale')
            AS last_purchase_at,
        COUNT(DISTINCT f.invoice_no) FILTER (WHERE f.transaction_status = 'valid_sale')
            AS frequency,
        COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'valid_sale'), 0)
            + COALESCE(SUM(f.line_revenue) FILTER (WHERE f.transaction_status = 'cancellation'), 0)
            AS monetary
    FROM warehouse.dim_customer c
    JOIN warehouse.fact_sales f ON f.customer_key = c.customer_key
    GROUP BY c.customer_key, c.customer_id
    HAVING COUNT(*) FILTER (WHERE f.transaction_status = 'valid_sale') > 0
),
scored AS (
    SELECT
        ct.*,
        (reference.reference_date - ct.last_purchase_at::date) AS recency_days,
        NTILE(4) OVER (ORDER BY (reference.reference_date - ct.last_purchase_at::date) DESC)
            AS recency_score,
        NTILE(4) OVER (ORDER BY ct.frequency ASC) AS frequency_score,
        NTILE(4) OVER (ORDER BY ct.monetary ASC) AS monetary_score
    FROM customer_txn ct
    CROSS JOIN reference
)
SELECT
    customer_key,
    customer_id,
    first_purchase_at,
    last_purchase_at,
    recency_days,
    frequency,
    monetary,
    recency_score,
    frequency_score,
    monetary_score,
    (recency_score + frequency_score + monetary_score) AS rfm_total_score,
    CASE
        WHEN recency_score >= 4 AND frequency_score >= 4 AND monetary_score >= 4 THEN 'Champions'
        WHEN recency_score >= 3 AND frequency_score >= 3 THEN 'Loyal'
        WHEN recency_score <= 2 AND frequency_score >= 3 THEN 'At risk'
        WHEN recency_score >= 3 AND frequency_score <= 2 THEN 'New / occasional'
        ELSE 'Other'
    END AS rfm_segment_heuristic
FROM scored;

-- Monthly cohort retention. Cohort month = month of a customer's first valid_sale
-- invoice. month_index 0 is the cohort's own acquisition month (trivially 100%
-- retained by definition — everyone in a cohort bought in their first month).
-- COUNT(DISTINCT customer_key) throughout, so multiple orders from one customer in one
-- month never inflate the retained-customer count.
--
-- Observation-window limitation (see docs/business_insights.md): the dataset ends
-- 2011-12-09. A cohort formed near the end has had little or no opportunity to show
-- retention in later months purely because those later months don't exist in the data
-- — dataset_last_month (below) lets a consumer of this view judge which cohorts have
-- had enough time to be meaningfully compared, rather than reading an unobserved
-- absence as confirmed churn.
CREATE OR REPLACE VIEW warehouse.v_customer_cohort_retention AS
WITH customer_first_month AS (
    SELECT
        f.customer_key,
        MIN(DATE_TRUNC('month', f.invoice_timestamp))::date AS cohort_month
    FROM warehouse.fact_sales f
    WHERE f.transaction_status = 'valid_sale' AND f.customer_key IS NOT NULL
    GROUP BY f.customer_key
),
activity AS (
    SELECT DISTINCT
        f.customer_key,
        DATE_TRUNC('month', f.invoice_timestamp)::date AS activity_month
    FROM warehouse.fact_sales f
    WHERE f.transaction_status = 'valid_sale' AND f.customer_key IS NOT NULL
),
cohort_activity AS (
    SELECT
        cfm.cohort_month,
        a.activity_month,
        (EXTRACT(YEAR FROM a.activity_month) - EXTRACT(YEAR FROM cfm.cohort_month)) * 12
            + (EXTRACT(MONTH FROM a.activity_month) - EXTRACT(MONTH FROM cfm.cohort_month))
            AS month_index,
        COUNT(DISTINCT a.customer_key) AS returning_customers
    FROM customer_first_month cfm
    JOIN activity a ON a.customer_key = cfm.customer_key AND a.activity_month >= cfm.cohort_month
    GROUP BY cfm.cohort_month, a.activity_month
),
cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT customer_key) AS cohort_size
    FROM customer_first_month
    GROUP BY cohort_month
),
bounds AS (
    SELECT DATE_TRUNC('month', MAX(invoice_timestamp))::date AS dataset_last_month
    FROM warehouse.fact_sales
    WHERE transaction_status = 'valid_sale'
)
SELECT
    ca.cohort_month,
    ca.activity_month,
    ca.month_index,
    cs.cohort_size,
    ca.returning_customers,
    ROUND(100.0 * ca.returning_customers / NULLIF(cs.cohort_size, 0), 2) AS retention_pct,
    b.dataset_last_month
FROM cohort_activity ca
JOIN cohort_size cs ON cs.cohort_month = ca.cohort_month
CROSS JOIN bounds b
ORDER BY ca.cohort_month, ca.activity_month;

-- =====================================================================================
-- D. TRANSACTION QUALITY / DUPLICATE SENSITIVITY
-- =====================================================================================

-- Side-by-side KPI comparison: complete dataset vs. the documented deduplicated view.
-- See v_valid_sales_deduplicated's own comment (006_views.sql) for its exact selection
-- rule and limitations before interpreting either row as "more correct".
CREATE OR REPLACE VIEW warehouse.v_duplicate_sensitivity AS
WITH full_data AS (
    SELECT
        COALESCE(SUM(line_revenue), 0) AS revenue,
        COUNT(DISTINCT invoice_no) AS order_count,
        COALESCE(SUM(quantity), 0) AS units_sold
    FROM warehouse.v_valid_sales
),
deduplicated AS (
    SELECT
        COALESCE(SUM(line_revenue), 0) AS revenue,
        COUNT(DISTINCT invoice_no) AS order_count,
        COALESCE(SUM(quantity), 0) AS units_sold
    FROM warehouse.v_valid_sales_deduplicated
)
SELECT
    'complete_dataset' AS dataset_version,
    f.revenue,
    f.order_count,
    f.units_sold,
    CASE WHEN f.order_count > 0 THEN ROUND(f.revenue / f.order_count, 2) ELSE NULL END
        AS average_order_value
FROM full_data f
UNION ALL
SELECT
    'deduplicated' AS dataset_version,
    d.revenue,
    d.order_count,
    d.units_sold,
    CASE WHEN d.order_count > 0 THEN ROUND(d.revenue / d.order_count, 2) ELSE NULL END
        AS average_order_value
FROM deduplicated d;

-- Single-row deltas (complete minus deduplicated) for convenience.
--
-- Written as a single scan of v_duplicate_sensitivity with conditional aggregation,
-- NOT four correlated scalar subqueries each re-selecting from it: measured via
-- EXPLAIN ANALYZE that the naive four-subquery version re-executes
-- v_valid_sales_deduplicated's window-function pass 4 times (once per output column)
-- — 3.4s total. This version evaluates the underlying views exactly once (~0.8s).
CREATE OR REPLACE VIEW warehouse.v_duplicate_sensitivity_delta AS
SELECT
    MAX(revenue) FILTER (WHERE dataset_version = 'complete_dataset')
        - MAX(revenue) FILTER (WHERE dataset_version = 'deduplicated') AS revenue_difference,
    MAX(order_count) FILTER (WHERE dataset_version = 'complete_dataset')
        - MAX(order_count) FILTER (WHERE dataset_version = 'deduplicated') AS order_count_difference,
    MAX(units_sold) FILTER (WHERE dataset_version = 'complete_dataset')
        - MAX(units_sold) FILTER (WHERE dataset_version = 'deduplicated') AS units_sold_difference,
    MAX(average_order_value) FILTER (WHERE dataset_version = 'complete_dataset')
        - MAX(average_order_value) FILTER (WHERE dataset_version = 'deduplicated')
        AS average_order_value_difference
FROM warehouse.v_duplicate_sensitivity;
