-- Section A: SALES PERFORMANCE
-- Standalone, runnable analysis queries. Where a reusable view already exists
-- (warehouse.v_monthly_revenue_growth, warehouse.v_revenue_by_country) these queries
-- use it directly rather than re-deriving the same logic — see sql/schema/007_phase5_views.sql
-- for the underlying CTEs/window functions.

-- A1. Headline totals: gross sales revenue, net revenue, total orders, AOV, units sold.
-- Net revenue = gross sales revenue + cancellation value (cancellation value is
-- already <= 0). potential_return and non_standard rows are excluded by policy (see
-- docs/kpi_definitions.md) — the 3 anomalous invoice-format rows are non_standard and
-- so never enter this figure.
SELECT
    COUNT(DISTINCT invoice_no) FILTER (WHERE transaction_status = 'valid_sale') AS total_orders,
    SUM(quantity) FILTER (WHERE transaction_status = 'valid_sale') AS units_sold,
    SUM(line_revenue) FILTER (WHERE transaction_status = 'valid_sale') AS gross_sales_revenue,
    SUM(line_revenue) FILTER (WHERE transaction_status = 'cancellation') AS cancellation_value,
    COALESCE(SUM(line_revenue) FILTER (WHERE transaction_status = 'valid_sale'), 0)
        + COALESCE(SUM(line_revenue) FILTER (WHERE transaction_status = 'cancellation'), 0)
        AS net_revenue,
    ROUND(
        (
            COALESCE(SUM(line_revenue) FILTER (WHERE transaction_status = 'valid_sale'), 0)
            + COALESCE(SUM(line_revenue) FILTER (WHERE transaction_status = 'cancellation'), 0)
        )
        / NULLIF(COUNT(DISTINCT invoice_no) FILTER (WHERE transaction_status = 'valid_sale'), 0),
        2
    ) AS average_order_value
FROM warehouse.fact_sales;

-- A2. Monthly revenue, month-over-month growth, and cumulative revenue — reusable view.
-- is_partial_month must be checked before reading any growth % as a genuine trend: the
-- final month's -70% MoM figure (see docs/business_insights.md) is a truncated-month
-- artefact (only 9 of 31 days observed), not a real December decline.
SELECT * FROM warehouse.v_monthly_revenue_growth ORDER BY year, month;

-- A3. Revenue by country, ranked (RANK() window function; the view already exposes
-- revenue_rank, this demonstrates re-deriving the rank inline for comparison).
SELECT
    country_name,
    order_count,
    gross_sales_revenue,
    cancellation_value,
    net_revenue,
    revenue_rank,
    ROUND(100.0 * net_revenue / SUM(net_revenue) OVER (), 2) AS pct_of_total_net_revenue
FROM warehouse.v_revenue_by_country
ORDER BY revenue_rank;

-- A4. Same headline figures, restricted to full (non-partial) months only — a fair
-- like-for-like comparison basis. In practice this only excludes December 2011: the
-- dataset's other edge, December 2010, starts exactly on the 1st and so is NOT
-- flagged partial (verified, not assumed — see v_monthly_revenue_growth's definition).
SELECT
    SUM(order_count) AS total_orders_full_months,
    SUM(net_revenue) AS net_revenue_full_months,
    ROUND(AVG(net_revenue), 2) AS average_monthly_net_revenue_full_months
FROM warehouse.v_monthly_revenue_growth
WHERE NOT is_partial_month;
