-- Section B: PRODUCT PERFORMANCE

-- B1. Top 10 products by revenue. Note: the #1 result by revenue is "DOT" (DOTCOM
-- POSTAGE) — a shipping charge, not a merchandise item (flag_non_standard_stock_code
-- = true for this stock_code). It is still a genuine, correctly-priced valid_sale line
-- (a customer really was charged this), so it is correctly included here — but it
-- should be called out explicitly wherever this ranking is presented, not silently
-- read as "our best-selling product".
SELECT stock_code, description, revenue, revenue_rank, quantity_rank, pct_of_total_revenue
FROM warehouse.v_product_performance
ORDER BY revenue_rank
LIMIT 10;

-- B2. Top 10 products by quantity sold. Ranking differs from B1 — revenue and
-- popularity-by-unit are not the same question. "23843" (PAPER CRAFT, LITTLE BIRDIE)
-- tops this list at 80,995 units, but 80,995 of those units are a SINGLE invoice line
-- (invoice 581483, one bulk order) — see B3 for the same finding surfaced directly.
SELECT stock_code, description, units_sold, revenue, revenue_rank, quantity_rank
FROM warehouse.v_product_performance
ORDER BY quantity_rank
LIMIT 10;

-- B3. Largest single order lines by quantity — a sanity check for outlier-driven
-- rankings before trusting B2 at face value.
SELECT
    f.source_row_id,
    f.invoice_no,
    p.stock_code,
    p.description,
    f.quantity,
    f.unit_price,
    f.line_revenue,
    f.invoice_timestamp
FROM warehouse.fact_sales f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
WHERE f.transaction_status = 'valid_sale'
ORDER BY f.quantity DESC
LIMIT 5;

-- B4. Revenue contribution: how much of total revenue comes from the top N products
-- (a running/cumulative-total window function, demonstrating concentration).
WITH ranked AS (
    SELECT stock_code, description, revenue, revenue_rank
    FROM warehouse.v_product_performance
)
SELECT
    stock_code,
    description,
    revenue,
    revenue_rank,
    SUM(revenue) OVER (ORDER BY revenue_rank ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        AS cumulative_revenue,
    ROUND(
        100.0 * SUM(revenue) OVER (ORDER BY revenue_rank ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            / SUM(revenue) OVER (),
        2
    ) AS cumulative_pct_of_total
FROM ranked
ORDER BY revenue_rank
LIMIT 20;

-- B5. Product ranking within each country — top 3 per country (ROW_NUMBER, since ties
-- should be broken deterministically for a fixed-size "top 3" list, unlike RANK which
-- the underlying view uses for a tie-transparent leaderboard).
SELECT country_name, stock_code, description, revenue, rank_within_country
FROM warehouse.v_product_country_rankings
WHERE rank_within_country <= 3
ORDER BY country_name, rank_within_country;

-- B6. Monthly sales trend for the top 5 products by all-time revenue.
SELECT t.stock_code, t.description, t.year, t.month, t.units_sold, t.revenue
FROM warehouse.v_product_monthly_trend t
WHERE t.stock_code IN (
    SELECT stock_code FROM warehouse.v_product_performance ORDER BY revenue_rank LIMIT 5
)
ORDER BY t.stock_code, t.year, t.month;

-- B7. Products most associated with cancellation activity.
SELECT stock_code, description, cancellation_count, cancellation_value,
       valid_sale_count, cancellation_rate_pct
FROM warehouse.v_product_cancellation_activity
ORDER BY cancellation_count DESC
LIMIT 10;
