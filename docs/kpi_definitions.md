# KPI Definitions

Every metric below states its exact formula, denominator, and how cancellations/returns
are treated, so results are reproducible and defensible in an interview. Definitions are
finalised in Phase 5 alongside the SQL that implements them; this is the planning
specification.

## Transaction classification (feeds every KPI below)

A row is classified as exactly one of:

| `transaction_type` | Rule |
|---|---|
| `cancellation` | `InvoiceNo` starts with `C` (and `Quantity` is negative). |
| `return` | `Quantity < 0` but `InvoiceNo` does **not** start with `C` (a negative-quantity line not flagged as a cancellation — logged for review, kept separate from true cancellations). |
| `questionable` | `UnitPrice <= 0`, or `StockCode`/`Description` indicates a non-product line (e.g. `POST`, `D`, `M`, `BANK CHARGES`, `DOT`), regardless of quantity. |
| `sale` | Everything else: positive `Quantity`, positive `UnitPrice`, a real product line. |

## Revenue

- **Line revenue** = `Quantity * UnitPrice` (only meaningful for `sale` rows; cancellations naturally net negative if included).
- **Gross sales revenue** = `SUM(Quantity * UnitPrice)` over rows where `transaction_type = 'sale'`.
- **Net sales revenue** = Gross sales revenue **+** `SUM(Quantity * UnitPrice)` over rows where `transaction_type = 'cancellation'` (cancellation amounts are negative, so this nets them off). `return` and `questionable` rows are excluded from both — documented as a deliberate choice, not silently dropped.

## Orders

- **Order** = one distinct `InvoiceNo`.
- **Order count** = `COUNT(DISTINCT InvoiceNo)` among `sale` rows (cancelled invoices are not counted as orders).
- **Average order value (AOV)** = Net sales revenue / Order count.

## Units

- **Units sold** = `SUM(Quantity)` over `sale` rows.

## Customers

- **Active customers** = `COUNT(DISTINCT CustomerID)` among `sale` rows with a non-null `CustomerID`. Rows with missing `CustomerID` are excluded from this and every customer-level metric — the exclusion rate (24.9% of rows) is reported alongside the metric, not hidden.
- **Repeat customer rate** = (number of customers with ≥ 2 distinct `InvoiceNo` on `sale` rows) / (total active customers). Denominator is active customers with known `CustomerID` only.

## Product ranking

- **Product revenue** = `SUM(Quantity * UnitPrice)` per `StockCode`, `sale` rows only.
- Ranked with `RANK()`/`ROW_NUMBER()` window functions in `sql/analysis/`.

## Cancellation / return rate

- **Cancellation rate** = (count of `cancellation` rows) / (count of `sale` + `cancellation` rows).
- Reported both by row count and by revenue value offset.

## Monthly revenue growth

- Revenue grouped by `DATE_TRUNC('month', InvoiceDate)`, using Net sales revenue.
- Month-over-month growth % = `(this_month - prev_month) / prev_month`, computed with a window function (`LAG`) in SQL — see `sql/analysis/`.

## RFM (customer segmentation)

- **Recency** = days between the dataset's max `InvoiceDate` and a customer's last `sale` invoice date.
- **Frequency** = count of distinct `sale` invoices per customer.
- **Monetary** = Net sales revenue attributable to that customer.
- Computed only for customers with a known `CustomerID`.
