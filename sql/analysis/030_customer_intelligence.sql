-- Section C: CUSTOMER INTELLIGENCE
--
-- Every query here is identity-dependent: it necessarily excludes the 24.93% of rows
-- with no CustomerID (see docs/kpi_definitions.md). This is stated once here rather
-- than repeated in every query's comment.

-- C1. Identified customers, and how many of them have at least one qualifying
-- (valid_sale) purchase (a customer can exist in dim_customer via a cancellation or
-- non_standard row alone, with zero qualifying purchases).
SELECT
    (SELECT COUNT(*) FROM warehouse.dim_customer) AS identified_customers,
    (SELECT COUNT(*) FROM warehouse.v_customer_rfm) AS customers_with_qualifying_purchase;

-- C2. Repeat customer rate: identified customers with >= 2 distinct valid_sale
-- invoices, as a share of all identified customers with >= 1 qualifying purchase.
WITH customer_orders AS (
    SELECT customer_key, COUNT(DISTINCT invoice_no) AS order_count
    FROM warehouse.fact_sales
    WHERE transaction_status = 'valid_sale' AND customer_key IS NOT NULL
    GROUP BY customer_key
)
SELECT
    COUNT(*) AS customers_with_qualifying_purchase,
    COUNT(*) FILTER (WHERE order_count >= 2) AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE order_count >= 2) / COUNT(*), 2) AS repeat_customer_rate_pct
FROM customer_orders;

-- C3. Purchase frequency distribution (how many customers ordered exactly N times).
WITH customer_orders AS (
    SELECT customer_key, COUNT(DISTINCT invoice_no) AS order_count
    FROM warehouse.fact_sales
    WHERE transaction_status = 'valid_sale' AND customer_key IS NOT NULL
    GROUP BY customer_key
)
SELECT order_count, COUNT(*) AS customer_count
FROM customer_orders
GROUP BY order_count
ORDER BY order_count;

-- C4. Average customer spend, and the distribution of spend via percentiles
-- (demonstrates PERCENTILE_CONT — spend is heavily right-skewed, so the mean alone is
-- a misleading "typical customer" figure; compare against the median below).
SELECT
    ROUND(AVG(monetary), 2) AS mean_customer_spend,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY monetary) AS median_customer_spend,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY monetary) AS p90_customer_spend,
    MIN(monetary) AS min_customer_spend,
    MAX(monetary) AS max_customer_spend
FROM warehouse.v_customer_rfm;

-- C5. Customer revenue distribution: share of total revenue held by the top 10%/20%
-- of customers by spend (a Pareto-style concentration check).
WITH ranked AS (
    SELECT
        customer_id,
        monetary,
        NTILE(10) OVER (ORDER BY monetary DESC) AS decile
    FROM warehouse.v_customer_rfm
)
SELECT
    decile,
    COUNT(*) AS customers_in_decile,
    SUM(monetary) AS decile_revenue,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS pct_of_total_revenue
FROM ranked
GROUP BY decile
ORDER BY decile;

-- C6. First and last purchase dates per customer (already computed in v_customer_rfm;
-- shown here directly for customers with the longest customer lifespan observed).
SELECT
    customer_id,
    first_purchase_at,
    last_purchase_at,
    (last_purchase_at::date - first_purchase_at::date) AS observed_lifespan_days,
    frequency,
    monetary
FROM warehouse.v_customer_rfm
ORDER BY observed_lifespan_days DESC
LIMIT 10;

-- C7. Customer lifetime value — defined here strictly as OBSERVED HISTORICAL REVENUE
-- within this dataset's window (net of the customer's own cancellations), NOT a
-- predicted/modelled future lifetime value. No churn or survival model is applied.
SELECT customer_id, monetary AS observed_historical_net_revenue, frequency AS order_count
FROM warehouse.v_customer_rfm
ORDER BY monetary DESC
LIMIT 10;

-- C8. RFM segmentation summary (a heuristic — see the view's own comment for caveats).
SELECT
    rfm_segment_heuristic,
    COUNT(*) AS customer_count,
    ROUND(AVG(recency_days), 1) AS avg_recency_days,
    ROUND(AVG(frequency), 1) AS avg_frequency,
    ROUND(AVG(monetary), 2) AS avg_monetary
FROM warehouse.v_customer_rfm
GROUP BY rfm_segment_heuristic
ORDER BY avg_monetary DESC;
