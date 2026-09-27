# KPI Definitions

Every metric below states its exact formula, denominator, and how cancellations/returns
are treated, so results are reproducible and defensible in an interview.

> **Status:** every definition below is **implemented and verified** against the real
> dataset. Phase 3 (`cleaning.py`) computes `transaction_status` and `line_revenue`;
> Phase 4 loads them into PostgreSQL; Phase 5 (`sql/schema/007_phase5_views.sql`,
> `sql/analysis/`) implements monthly growth, RFM, cohort retention, and duplicate
> sensitivity as SQL views, reconciled against independent Python calculations in
> `tests/test_analysis.py`. Real results: `docs/business_insights.md`.

## Transaction classification (feeds every KPI below)

Every row gets exactly one `transaction_status`, decided by this precedence (highest
first) — implemented in `cleaning.classify_transactions`:

| Precedence | `transaction_status` | Rule |
|---|---|---|
| 1 (highest) | `cancellation` | `invoice_no` starts with `C` — the dataset's documented convention. |
| 2 | `potential_return` | `quantity < 0` and not a cancellation. |
| 3 | `non_standard` | `quantity >= 0`, but `unit_price <= 0`, `quantity == 0`, an invalid/missing `invoice_date`, or an `invoice_no` not matching the normal `^C?\d{6}$` pattern. |
| 4 (default) | `valid_sale` | Everything else: positive quantity, positive price, a normally-formatted invoice, not cancelled. |

Cancellation outranks potential-return so the two are never conflated (both are
negative-quantity, but only one is a formally cancelled invoice). Potential-return
outranks non-standard so a negative-quantity row is never relabelled away from
"potential_return" merely because it also has a zero price — **verified against the
real dataset: all 1,336 potential-return rows have `unit_price == 0` and no
`customer_id`, and this is treated as a genuine characteristic of the category, not
grounds to reclassify it** (see `docs/data_dictionary.md`).

**Verified exceptions to the documented conventions** (computed, not assumed):
- Cancellation-prefixed invoices with non-negative quantity: **0** in the real dataset.
- Rows with a non-standard `invoice_no` format: **3** — a set of "Adjust bad debt"
  manual accounting entries (`InvoiceNo` like `A563185`, `StockCode = 'B'`), one of
  which has a *positive* price and quantity and would otherwise look like an ordinary
  sale. Caught only because of the anomalous invoice format check.

**Non-exclusive flags** (a row may carry several, independent of `transaction_status`):
`flag_missing_customer_id`, `flag_missing_description`, `flag_non_positive_price`,
`flag_zero_quantity`, `flag_duplicate_candidate`, `flag_non_standard_invoice_format`,
`flag_non_standard_stock_code` (a non-product code like `POST`/`DOT`/`BANK CHARGES` —
informational only, does **not** change `transaction_status`, since many such lines,
e.g. postage, are genuine correctly-priced charges).

## Revenue

- **Line revenue** (`line_revenue`) = `quantity * unit_price` for every row, computed
  via Python `Decimal` (converted through `str()` to avoid inheriting float64 binary
  representation error) and quantized to whole pence with `ROUND_HALF_UP`.
- **Gross sales revenue** = `SUM(line_revenue)` over `valid_sale` rows only.
- **Cancellation value** = `SUM(line_revenue)` over `cancellation` rows (verified
  always <= 0 in this dataset, since there are 0 exceptions to the negative-quantity
  convention).
- **Potential return value** = `SUM(line_revenue)` over `potential_return` rows —
  verified to equal **exactly £0.00** in this dataset, since every such row has
  `unit_price == 0`. This is why potential returns are *not* treated as confirmed
  refunds: there is no monetary value to net off.
- **Non-standard value** = `SUM(line_revenue)` over `non_standard` rows — reported for
  transparency, excluded from net revenue (these aren't verified genuine transactions).
- **Net revenue** = Gross sales revenue **+** Cancellation value. `potential_return` and
  `non_standard` rows are excluded by policy, not silently dropped — both are reported
  separately in `reports/cleaning_summary.md`.
- No profit, margin, or shipping cost is calculated — the source dataset has no cost data.

## Duplicate policy

Exact-duplicate rows (identical across every original column) are **flagged**
(`flag_duplicate_candidate`), never auto-dropped. Verified: 10,147 rows across 4,879
groups (largest group: 20 identical rows). Retaining risks double-counting in a naive
`SUM`; dropping risks deleting a genuine repeat purchase (same product/qty/price in the
same session). Each downstream query decides deliberately using the flag.

## Orders

- **Order** = one distinct `invoice_no`.
- **Order count** = `COUNT(DISTINCT invoice_no)` among `valid_sale` rows (cancelled
  invoices are not counted as orders).
- **Average order value (AOV)** = Net revenue / Order count.

## Units

- **Units sold** = `SUM(quantity)` over `valid_sale` rows.

## Customers

- **Active customers** = `COUNT(DISTINCT customer_id)` among `valid_sale` rows with a
  non-null `customer_id`. Rows with missing `customer_id` are excluded from this and
  every customer-level metric — the exclusion rate is reported alongside the metric,
  not hidden (verified: 135,080 rows / 24.93% overall have no `customer_id`).
- **Repeat customer rate** = (customers with >= 2 distinct `invoice_no` on `valid_sale`
  rows) / (total active customers). Denominator is active customers with a known
  `customer_id` only.

## Product ranking

- **Product revenue** = `SUM(line_revenue)` per `stock_code`, `valid_sale` rows only.
- Ranked with `RANK()`/`ROW_NUMBER()` window functions in `sql/analysis/` (Phase 5).

## Cancellation / return rate

- **Cancellation rate** = (count of `cancellation` rows) / (count of `valid_sale` +
  `cancellation` rows).
- Reported both by row count and by revenue value offset (see Revenue above).

## Monthly revenue growth (implemented — `warehouse.v_monthly_revenue_growth`)

- Revenue grouped by `DATE_TRUNC('month', invoice_date)`, using Net revenue.
- Month-over-month growth % = `(this_month - prev_month) / prev_month`, computed with
  `LAG()`. `NULL` for the first month (no previous period) and whenever the previous
  month's net revenue is exactly 0 (avoids a division-by-zero).
- Cumulative revenue = a running `SUM() OVER (ORDER BY year, month ROWS BETWEEN
  UNBOUNDED PRECEDING AND CURRENT ROW)`.
- **`is_partial_month`**: `TRUE` only if the month is the dataset's very first or very
  last calendar month **and** the dataset's actual min/max date doesn't reach that
  month's calendar boundary — verified against the real data, not assumed. The
  dataset's first month (2010-12) starts exactly on the 1st and is correctly **not**
  flagged, even though its own last recorded sale is the 23rd (a business/holiday gap,
  not a truncated observation window); the last month (2011-12) **is** flagged (last
  recorded sale: the 9th).

## RFM (customer segmentation, implemented — `warehouse.v_customer_rfm`)

- **Recency** = days between a reference date and a customer's last `valid_sale`
  invoice date. Reference date = `MAX(invoice_timestamp) + 1 day` **across the whole
  dataset** — derived from the data, not wall-clock "today", so results are
  reproducible regardless of when the query runs.
- **Frequency** = count of distinct `valid_sale` invoices per customer.
- **Monetary** = that customer's `valid_sale` revenue, netted against their **own**
  `cancellation` revenue (both attributed via `customer_key`). 383 of 9,288
  cancellation rows (4.1%) have no `customer_id` and so cannot be netted at the
  customer level — they are still counted in organisation-wide net revenue.
- Computed only for customers with a known `customer_id` **and** at least one
  `valid_sale` purchase (34 of 4,372 identified customers have none — e.g. a customer
  whose only recorded activity is a cancellation — and are excluded).
- **Scores**: `NTILE(4)` quartiles per dimension (4 = best: most recent, most
  frequent, highest spend). `rfm_segment_heuristic` is a simple score-threshold
  labelling (e.g. `Champions` = top quartile on all three) — **a heuristic, not a
  validated behavioural segmentation**. Treat it as a starting point for investigation.

## Cohort retention (implemented — `warehouse.v_customer_cohort_retention`)

- **Cohort month** = the calendar month of a customer's first `valid_sale` invoice.
- **Activity month** = any calendar month in which that customer has a `valid_sale`
  invoice (including the cohort month itself, `month_index = 0`, trivially 100%).
- **Cohort size** = `COUNT(DISTINCT customer_key)` in that cohort.
- **Retention %** = `COUNT(DISTINCT customer_key)` active in a given activity month /
  cohort size — distinct customers throughout, so multiple orders from one customer in
  one month never inflate the retained count.
- **Observation-window limitation**: the dataset ends 2011-12-09. A cohort formed near
  that date has had little or no chance to show retention in later months simply
  because those months aren't in the data — `dataset_last_month` is exposed on the view
  so this is never mistaken for confirmed churn.

## Duplicate sensitivity (implemented — `warehouse.v_duplicate_sensitivity[_delta]`)

Compares headline KPIs (revenue, order count, units sold, AOV) computed from the
complete dataset vs. `v_valid_sales_deduplicated` (see that view's own comment in
`sql/schema/006_views.sql` for its exact selection rule and limitations). Verified on
the real dataset: revenue -0.24%, units -0.29%, AOV -0.24%, order count unchanged —
neither figure is asserted as "the true" one; see `docs/business_insights.md`.
