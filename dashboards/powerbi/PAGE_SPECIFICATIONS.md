# Dashboard Page Specifications

Design system: clean/spacious layout, one accent colour family for KPI cards, a single
consistent categorical palette for charts (do not mix chart colour schemes between
pages), GBP `£#,##0.00` for currency, `0.0%` for percentages, a visible "Historical
data: 2010-12-01 to 2011-12-09 — not a live feed" caption on every page (footer or
header), and a page-level date/country slicer pair on Pages 1-2 (Page 3 uses a
segment slicer instead of country; Page 4 has no slicers — data quality should always
show the whole dataset).

## Page 1 — Executive Overview

**Purpose**: a stakeholder's first view — headline numbers and the overall trend, at a
glance, in under 10 seconds.

| Visual | Type | Fields / Measure | Notes |
|---|---|---|---|
| Net Revenue | Card | `[Net Revenue]` | Primary KPI, largest card, top-left |
| Gross Sales Revenue | Card | `[Gross Sales Revenue]` | |
| Total Orders | Card | `[Total Orders]` | |
| Average Order Value | Card | `[Average Order Value]` | |
| Active Customers | Card | `[Active Customers]` | |
| Monthly Revenue Trend | Line chart | X: `v_monthly_revenue_growth[month_start]`; Y: `net_revenue` | Partial month (Dec 2011) rendered as a **dashed line segment / hollow marker**, distinct from solid prior months — see "Partial-month handling" below |
| Revenue by Country | Bar chart (horizontal) | X: `dim_country[country_name]`; Y: `[Net Revenue]` | Top 10 countries; UK will dominate visually — consider a "exclude UK" toggle bookmark for readability of the smaller markets |
| Top Products by Revenue | Table | `dim_product[stock_code]`, `[description]`, `[Product Revenue]`, `[Product Revenue Contribution %]` | Top 10 by `[Product Revenue Rank]`; **flag row for `DOT`** (see Page 2 — the same non-merchandise caption applies here) |
| Filters | Slicers | `dim_date[date_value]` (range), `dim_country[country_name]` | |

**Partial-month handling on this page**: bind the Line chart's data point colour/style
to `v_monthly_revenue_growth[is_partial_month]` (a conditional formatting rule: TRUE ->
dashed/grey, FALSE -> solid/accent colour). Add a small text visual under the chart
bound to `[Partial Month Warning Text]`, which is empty (renders nothing) unless the
current filter includes a partial month.

## Page 2 — Product and Sales Performance

**Purpose**: which products drive revenue and volume, with the two known distortions
(a postage line topping the revenue ranking; a single bulk order topping the quantity
ranking) surfaced rather than hidden.

| Visual | Type | Fields / Measure | Notes |
|---|---|---|---|
| Top Products by Revenue | Bar chart | `dim_product[stock_code]`+`[description]`, `[Product Revenue]` | Top 15; conditional formatting/icon on any row where `[Is Non-Merchandise Stock Code]` = TRUE |
| Top Products by Quantity | Bar chart | `dim_product[stock_code]`+`[description]`, `Units Sold` (filtered to valid_sale) | Top 15 |
| **Caption (required, not optional)** | Text box | static | *"DOT (DOTCOM POSTAGE) is a shipping charge, not a merchandise item, and is excluded from a 'top-selling product' interpretation. The top quantity result (23843, 80,995 units) is driven by a single bulk order (invoice 581483) rather than broad demand — see docs/business_insights.md."* |
| Product Revenue Contribution | Treemap or 100% stacked bar | `dim_product[stock_code]`, `[Product Revenue Contribution %]` | Visualises concentration; top 10 products vs "All other products" bucket |
| Monthly Product Trend | Line chart | X: `dim_date[date_value]` (by month); Y: `[Product Revenue]`; Legend: `dim_product[description]` | Filterable to a product selection via the table below (Top Products by Revenue) acting as a slicer through cross-filtering |
| Revenue by Country (Product-filtered) | Matrix | Rows: `dim_product[description]`; Columns: `dim_country[country_name]`; Values: `[Product Revenue]` | Top 10 products x top 5 countries only, to keep the matrix readable |
| Cancellation Activity | Table | `dim_product[stock_code]`, `[description]`, `Cancellations Count` (product-filtered), `Cancellation Value` (product-filtered) | Sorted by cancellation count descending; surfaces `M` (Manual, 244), `22423` (Regency Cakestand, 181), `POST` (126) |
| Filters | Slicers | `dim_date[date_value]` (range), `dim_country[country_name]` | |

## Page 3 — Customer Intelligence

**Purpose**: who the customers are, how concentrated revenue is among them, and a
clearly-labelled RFM heuristic — never presented as a validated behavioural model.

| Visual | Type | Fields / Measure | Notes |
|---|---|---|---|
| Identified Customers | Card | `COUNTROWS(dim_customer)` | 4,372 |
| Customers with a Qualifying Purchase | Card | `COUNTROWS(v_customer_rfm)` | 4,338 — caption: *"34 identified customers have no qualifying (valid_sale) purchase and are excluded from RFM/CLV below"* |
| Repeat Customer Rate | Card | `[Repeat Customer Rate]` | 65.58% |
| Mean vs. Median Spend | Two cards, side by side | `AVERAGE(v_customer_rfm[monetary])`, `MEDIANX(v_customer_rfm, v_customer_rfm[monetary])` | **Always shown together** — see DAX_MEASURES.md |
| Top 10% Revenue Concentration | Card | `[Customer Revenue Concentration (Top 10%)]` | 59.80% |
| Customer Revenue Distribution | Histogram / decile bar chart | `v_customer_rfm[monetary]` binned, or a decile table (`NTILE`-equivalent via Power Query grouping) | Shows the right-skew directly |
| RFM Segmentation | Scatter chart | X: `recency_days`; Y: `frequency`; Size: `monetary`; Legend/colour: `rfm_segment_heuristic` | **Page/visual title must include the word "heuristic"** — do not title this simply "Customer Segments" |
| RFM Segment Summary | Table | `rfm_segment_heuristic`, count, avg recency/frequency/monetary | One row per segment (5 rows) |
| Customer Cohort Retention | Matrix (heatmap) | Rows: `cohort_month`; Columns: `month_index`; Values: `retention_pct`, colour-scaled | Conditional formatting: grey out any cell where `activity_month > dataset_last_month` minus a reasonable maturity window is not yet reached — see caption below |
| **Caption (required)** | Text box | static | *"RFM segments are a scoring heuristic (quartile thresholds on Recency/Frequency/Monetary), not a validated behavioural model. 'Customer lifetime value' here means observed historical revenue within this dataset's window, not a predicted future value. Cohorts formed in the dataset's final months (e.g. Nov/Dec 2011) have had little or no chance to show retention — their low/blank later-month cells reflect an unobserved period, not confirmed churn."* |
| Filters | Slicer | `v_customer_rfm[rfm_segment_heuristic]` | No country slicer on this page — RFM/cohort are customer-grain, not transaction-grain |

## Page 4 — Transaction Quality and Data Reliability

**Purpose**: make the data's own limitations a first-class part of the dashboard, not
an appendix. No date/country slicers — this page always reports on the whole dataset.

| Visual | Type | Fields / Measure | Notes |
|---|---|---|---|
| Total Source Records | Card | `[Total Source Records]` | 541,909 |
| Valid Sales / Cancellations / Potential Returns / Non-Standard | 4 cards in a row | respective `*Count` measures | Show both count and % of total on each card |
| Transaction Status Breakdown | Donut or 100% stacked bar | `fact_sales[transaction_status]`, `COUNTROWS` | Visual proportion check against the 4 cards above |
| Missing Customer Identifier Rate | Card + gauge | `[Missing Customer ID Rate]` | 24.93% |
| Duplicate-Candidate Records | Card | `[Duplicate Candidate Count]` | 10,147 |
| Anomalous Invoice-Format Records | Card, visually distinct (e.g. warning-coloured border) | `[Anomalous Invoice Format Count]` | 3 — **must be its own visible card**, not merged into Non-Standard Count |
| Duplicate Sensitivity Comparison | Clustered bar chart | `v_duplicate_sensitivity[dataset_version]` (X), `revenue`/`order_count`/`units_sold`/`average_order_value` (small multiples or 4 side-by-side charts) | Both bars shown; neither labelled "correct" |
| **Caption (required, exact wording)** | Text box | static | *"Duplicate-candidate rows are preserved in this dashboard's default figures, not silently removed. The 'deduplicated' comparison above is one possible sensitivity view (keeps the first occurrence per exact-match group) — it is not asserted as more accurate; removing these rows risks discarding genuine repeat purchases in the same session. Difference: revenue -0.24%, units -0.29%, AOV -0.24%, orders unchanged."* |
| Negative Quantity Caption | Text box | static | *"Negative-quantity rows are split into two distinct, non-overlapping categories: `cancellation` (a formally cancelled invoice) and `potential_return` (negative quantity, not cancelled). Neither is automatically treated as a confirmed refund — every `potential_return` row in this dataset carries £0.00 in value (verified), so there is no refund amount being netted anywhere."* |

## Cross-page consistency rules

- Colour: `valid_sale` = brand accent; `cancellation` = amber/warning; `potential_return`
  = a distinct neutral (not red — it is not a confirmed loss); `non_standard` = grey.
  Reuse this mapping everywhere `transaction_status` appears as a legend.
- Every currency value: `£#,##0.00`. Every rate/percentage: `0.0%` (one decimal — the
  underlying figures are precise to 2dp but a dashboard percentage rarely needs more).
- Every page keeps the reporting-period caption ("Historical data: 2010-12-01 to
  2011-12-09 — not a live feed") visible without scrolling.
