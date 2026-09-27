# DAX Measures

Every measure below is a direct translation of an already-implemented, already-verified
SQL definition (`docs/kpi_definitions.md`) — none of this is new business logic invented
for Power BI. Each measure lists its **expected value on the full, unfiltered dataset**,
computed by the equivalent SQL query, so a report author can verify their finished card
matches before trusting it. `DIVIDE()` is used everywhere a denominator could be zero or
blank (a single customer/product/month slicer selection can easily produce one).

All measures assume they live in a dedicated `_Measures` table (a Power BI convention:
an empty table with no columns, existing only to hold measures tidily) unless noted.

## Sales performance

```dax
Gross Sales Revenue =
CALCULATE(
    SUM(fact_sales[line_revenue]),
    fact_sales[transaction_status] = "valid_sale"
)
-- Expected (unfiltered): £10,655,622.48
-- SQL: SUM(line_revenue) FILTER (WHERE transaction_status='valid_sale') FROM fact_sales

Cancellation Value =
CALCULATE(
    SUM(fact_sales[line_revenue]),
    fact_sales[transaction_status] = "cancellation"
)
-- Expected (unfiltered): -£896,812.49

Net Revenue =
[Gross Sales Revenue] + [Cancellation Value]
-- Expected (unfiltered): £9,758,809.99
-- potential_return and non_standard rows are excluded by construction (neither
-- measure above includes them) — not silently dropped, they simply aren't part of
-- this KPI's definition (see docs/kpi_definitions.md).

Total Orders =
CALCULATE(
    DISTINCTCOUNT(fact_sales[invoice_no]),
    fact_sales[transaction_status] = "valid_sale"
)
-- Expected (unfiltered): 19,959
-- A cancelled invoice is not counted as an order, matching the SQL definition.

Average Order Value =
DIVIDE([Net Revenue], [Total Orders])
-- Expected (unfiltered): £488.94
-- DIVIDE returns BLANK() if Total Orders is 0 (e.g. a filter context with no valid
-- sales at all), never a division error.

Units Sold =
CALCULATE(
    SUM(fact_sales[quantity]),
    fact_sales[transaction_status] = "valid_sale"
)
-- Expected (unfiltered): 5,588,375
```

## Growth and trend (used against `v_monthly_revenue_growth`, NOT `fact_sales`)

The month-over-month growth %, cumulative revenue, and partial-month flag are **already
computed in SQL** (`v_monthly_revenue_growth` — `LAG()`, a running `SUM() OVER`, and a
genuinely-derived boundary check). Re-deriving these in DAX over `fact_sales` risks
subtly recreating the partial-month logic incorrectly; instead, source the trend chart
directly from the imported `v_monthly_revenue_growth` table's own columns
(`net_revenue`, `month_over_month_growth_pct`, `cumulative_net_revenue`,
`is_partial_month`) — no DAX measure needed for these at all. The only DAX added here is
presentation logic for the partial-month warning:

```dax
Selected Period Has Partial Month =
VAR HasPartial =
    CALCULATE(
        MAX(v_monthly_revenue_growth[is_partial_month]),
        ALLSELECTED(v_monthly_revenue_growth)
    )
RETURN
    HasPartial = TRUE()
-- Drives the visible warning banner (Phase 6, section 8). TRUE whenever the current
-- page/visual filter context includes at least one partial month.

Partial Month Warning Text =
IF(
    [Selected Period Has Partial Month],
    "⚠ Selected period includes an incomplete month (data ends part-way through) — month-over-month % for that month is not a like-for-like comparison.",
    ""
)
-- Bind this to a Card/Text visual's conditional visibility or directly as its value;
-- an empty string collapses to nothing shown when no partial month is in view.
```

## Customer intelligence

```dax
Active Customers =
CALCULATE(
    DISTINCTCOUNT(fact_sales[customer_key]),
    fact_sales[transaction_status] = "valid_sale",
    NOT ISBLANK(fact_sales[customer_key])
)
-- Expected (unfiltered): 4,338 (customers with >= 1 valid_sale; matches
-- COUNT(*) FROM v_customer_rfm exactly, since that view uses the same filter).
-- The explicit NOT ISBLANK guards against DISTINCTCOUNT otherwise counting a
-- single BLANK as one "customer" for the 135,080 rows with no CustomerID.

Repeat Customer Rate =
VAR CustomersWithOrders =
    CALCULATE(
        DISTINCTCOUNT(fact_sales[customer_key]),
        fact_sales[transaction_status] = "valid_sale",
        NOT ISBLANK(fact_sales[customer_key])
    )
VAR RepeatCustomers =
    CALCULATE(
        DISTINCTCOUNT(fact_sales[customer_key]),
        FILTER(
            VALUES(fact_sales[customer_key]),
            CALCULATE(
                DISTINCTCOUNT(fact_sales[invoice_no]),
                fact_sales[transaction_status] = "valid_sale"
            ) >= 2
        ),
        fact_sales[transaction_status] = "valid_sale",
        NOT ISBLANK(fact_sales[customer_key])
    )
RETURN
    DIVIDE(RepeatCustomers, CustomersWithOrders)
-- Expected (unfiltered): 65.58% (2,845 of 4,338)
-- This measure is intentionally written directly over fact_sales (not
-- v_customer_rfm.frequency) so it stays correct under an arbitrary date/country
-- filter — a pre-aggregated frequency column would not reflect a partial-period
-- filter selection.

Average Customer Spend =
AVERAGE(v_customer_rfm[monetary])
-- Expected (unfiltered): £1,915.74 (mean). Also add a Median Customer Spend measure
-- using MEDIANX(v_customer_rfm, v_customer_rfm[monetary]) = £655.34 — the two
-- should always be shown together (see docs/business_insights.md: the mean is
-- nearly 3x the median due to heavy right-skew; showing only the mean misrepresents
-- the "typical" customer).

Customer Revenue Concentration (Top 10%) =
VAR Decile1Customers =
    TOPN(
        ROUNDUP(COUNTROWS(v_customer_rfm) * 0.1, 0),
        v_customer_rfm,
        v_customer_rfm[monetary],
        DESC
    )
VAR Decile1Revenue = SUMX(Decile1Customers, v_customer_rfm[monetary])
RETURN
    DIVIDE(Decile1Revenue, SUM(v_customer_rfm[monetary]))
-- Expected (unfiltered): 59.80%
```

**Important — do not double-count**: `v_customer_rfm[monetary]` is already a
per-customer *total*. Never place it in the same visual alongside a `fact_sales`-based
revenue measure summed by the same customer — pick one source per visual. The RFM page
(Page 3) should source Recency/Frequency/Monetary/segment entirely from
`v_customer_rfm`'s own columns, not recomputed measures.

## Product and revenue contribution

```dax
Product Revenue =
CALCULATE(
    SUM(fact_sales[line_revenue]),
    fact_sales[transaction_status] = "valid_sale"
)
-- Used in a table/bar visual grouped by dim_product[stock_code]/[description].
-- Expected top row (unfiltered): stock_code "DOT" (DOTCOM POSTAGE), £206,248.77 —
-- see the Page 2 spec for why this must be visually flagged as a shipping charge.

Product Revenue Rank =
RANKX(ALL(dim_product), [Product Revenue], , DESC)

Product Revenue Contribution % =
DIVIDE([Product Revenue], CALCULATE([Product Revenue], ALL(dim_product)))
-- % of total revenue held by the product(s) in the current filter context.

Is Non-Merchandise Stock Code =
SELECTEDVALUE(dim_product[stock_code]) IN {"POST", "DOT", "M", "D", "S", "C2",
    "BANK CHARGES", "AMAZONFEE", "CRUK", "PADS", "B"}
    || NOT(ISNUMBER(VALUE(LEFT(SELECTEDVALUE(dim_product[stock_code]), 1))))
-- A presentation-layer flag (mirrors fact_sales.flag_non_standard_stock_code, which
-- already exists per-row in SQL) for a visual badge/icon on Page 2's product table —
-- prefer sourcing flag_non_standard_stock_code directly from fact_sales where
-- possible; this DAX version is provided for a product-grain visual that has no
-- fact_sales row context of its own.
```

## Data quality (Page 4)

```dax
Total Source Records = COUNTROWS(fact_sales)
-- Expected: 541,909

Valid Sales Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[transaction_status] = "valid_sale")
-- Expected: 530,103 (97.82%)

Cancellations Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[transaction_status] = "cancellation")
-- Expected: 9,288 (1.71%)

Potential Returns Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[transaction_status] = "potential_return")
-- Expected: 1,336 (0.25%) — NOT labelled "confirmed refunds": every one of these rows
-- has UnitPrice = 0 in this dataset (verified in Phase 3), so there is no refund
-- amount being netted off; the status only means "negative quantity, uncancelled".

Non-Standard Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[transaction_status] = "non_standard")
-- Expected: 1,182 (0.22%) — includes the 3 anomalous-invoice-format rows (see below).

Anomalous Invoice Format Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[flag_non_standard_invoice_format] = TRUE)
-- Expected: 3 — must be shown as its own card/row on Page 4, not folded silently into
-- the Non-Standard Count above, so these specific 3 "Adjust bad debt" rows stay
-- individually identifiable per the brief.

Missing Customer ID Rate =
DIVIDE(
    CALCULATE(COUNTROWS(fact_sales), fact_sales[flag_missing_customer_id] = TRUE),
    COUNTROWS(fact_sales)
)
-- Expected: 24.93%

Duplicate Candidate Count =
CALCULATE(COUNTROWS(fact_sales), fact_sales[flag_duplicate_candidate] = TRUE)
-- Expected: 10,147

Duplicate Revenue Sensitivity % =
VAR CompleteRevenue =
    CALCULATE(
        MAX(v_duplicate_sensitivity[revenue]),
        v_duplicate_sensitivity[dataset_version] = "complete_dataset"
    )
VAR DedupRevenue =
    CALCULATE(
        MAX(v_duplicate_sensitivity[revenue]),
        v_duplicate_sensitivity[dataset_version] = "deduplicated"
    )
RETURN
    DIVIDE(CompleteRevenue - DedupRevenue, CompleteRevenue)
-- Expected: 0.24% — present alongside both raw figures (£10,655,622.48 vs
-- £10,630,496.89), NEVER as a single number implying one version is "correct"; see
-- Page 4 spec for the required caption text.
```

## Reconciliation checklist (do this after building the model)

For each measure above, place it in a Card visual with **no filters applied** and
compare against the "Expected (unfiltered)" value. All expected values were computed
by the actual SQL queries in `sql/analysis/` and verified in
`docs/business_insights.md` / `tests/test_analysis.py` against a live database — if a
DAX card disagrees, the mismatch is in the Power BI model (a wrong filter, an
un-related table, a data-type import issue), not in the source data.
