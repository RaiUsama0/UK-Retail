# Business Insights

Every figure below is reproducible by running the query cited next to it (all in
`sql/analysis/` or the views in `sql/schema/006_views.sql` / `007_phase5_views.sql`)
against the live warehouse. Nothing here is invented or estimated. Where a number
could be misread, the finding is stated alongside the check that was done to verify
it isn't an artefact (a partial month, an outlier order, a truncated observation
window).

**Scope:** the complete `fact_sales` table (541,909 rows), unless a section says
otherwise. `valid_sale` = ordinary qualifying sales; `cancellation` = formally
cancelled invoices; `potential_return` and `non_standard` are reported separately and
excluded from revenue KPIs (see `docs/kpi_definitions.md` for the exact precedence
rule). The 3 anomalous-invoice-format rows are `non_standard` and never enter any
figure below.

## Executive summary

- **Net revenue: £9,758,809.99** over 2010-12-01 to 2011-12-09 (gross sales
  £10,655,622.48, less £896,812.49 of cancellations), across **19,959 orders**
  (average order value **£488.94**).
- The business is heavily **UK-concentrated** (net revenue £8,198,868.42, 84% of the
  total) with a long tail of European markets.
- **65.58%** of identified customers (2,845 of 4,338 with a qualifying purchase) are
  repeat buyers — a strong retention signal, though see the Customer behaviour caveat
  on cohorts below.
- Revenue is **heavily concentrated**: the top 10% of identified customers by spend
  account for **59.80%** of customer-attributable revenue.
- **December 2011 is a partial month** (data ends the 9th) — its -70% month-over-month
  revenue "decline" is a truncation artefact, not a real trend, and must not be
  reported as one.

## Sales performance

_Query: `sql/analysis/010_sales_performance.sql`_

| Metric | Value |
|---|---|
| Gross sales revenue | £10,655,622.48 |
| Cancellation value | -£896,812.49 |
| **Net revenue** | **£9,758,809.99** |
| Total orders | 19,959 |
| Average order value | £488.94 |
| Units sold | 5,588,375 |

Monthly net revenue and month-over-month growth (`v_monthly_revenue_growth`):

| Month | Net revenue | MoM growth | Partial? |
|---|---|---|---|
| 2010-12 | £748,957.02 | — (first month) | No |
| 2011-01 | £560,000.26 | -25.23% | No |
| 2011-02 | £498,062.65 | -11.06% | No |
| 2011-03 | £683,267.08 | +37.18% | No |
| 2011-04 | £493,207.12 | -27.82% | No |
| 2011-05 | £723,333.51 | +46.66% | No |
| 2011-06 | £691,123.12 | -4.45% | No |
| 2011-07 | £681,300.11 | -1.42% | No |
| 2011-08 | £693,742.57 | +1.83% | No |
| 2011-09 | £1,019,687.62 | +46.98% | No |
| 2011-10 | £1,070,704.67 | +5.00% | No |
| 2011-11 | £1,461,756.25 | +36.52% | No |
| 2011-12 | £433,668.01 | **-70.33%** | **Yes — 9 of 31 days** |

**Observed pattern, not a claimed cause:** revenue rises through autumn 2011 (Sept-Nov),
consistent with pre-Christmas ordering season for a gift retailer — this is a plausible
explanation given the business type, not a proven causal finding (no marketing spend,
promotions calendar, or macroeconomic data is available to confirm it). December
2010 was checked and confirmed genuinely NOT partial (the observation window starts
exactly on the 1st) — its own sales stop on the 23rd, which is a normal
holiday-period business gap, not a data truncation.

Revenue by country, top 5 (`v_revenue_by_country`):

| Country | Net revenue | Orders |
|---|---|---|
| United Kingdom | £8,198,868.42 | 18,018 |
| Netherlands | £284,661.54 | 94 |
| EIRE | £263,276.82 | 288 |
| Germany | £221,698.21 | 457 |
| France | £197,403.90 | 392 |

## Product performance

_Query: `sql/analysis/020_product_performance.sql`_

Top 5 products by revenue (`v_product_performance`):

| Stock code | Description | Revenue | % of total | Quantity rank |
|---|---|---|---|---|
| DOT | DOTCOM POSTAGE | £206,248.77 | 1.94% | 1,520th |
| 22423 | REGENCY CAKESTAND 3 TIER | £174,484.74 | 1.64% | 40th |
| 23843 | PAPER CRAFT, LITTLE BIRDIE | £168,469.60 | 1.58% | 1st |
| 85123A | WHITE HANGING HEART T-LIGHT HOLDER | £104,518.80 | 0.98% | 6th |
| 47566 | PARTY BUNTING | £99,504.33 | 0.93% | 22nd |

**Two findings that need interpretation, not face-value reporting:**
- The #1 product by revenue, `DOT` (DOTCOM POSTAGE), is a **shipping charge**, not a
  merchandise item (`flag_non_standard_stock_code = true`). It is a genuine,
  correctly-priced `valid_sale` line — a customer really was charged this — so it's
  correctly included, but presenting it as "our best-selling product" without
  qualification would mislead a stakeholder.
- The #1 product by quantity, `23843` (PAPER CRAFT, LITTLE BIRDIE, 80,995 units), owes
  nearly all of that volume to a **single bulk order** (invoice `581483`, 80,995 units
  at £2.08 each, placed 2011-12-09 — checked directly against the fact row). Reporting
  "our top seller by volume" without this context would overstate organic demand.

Products most associated with cancellation activity (`v_product_cancellation_activity`):
`M` (Manual, a manual adjustment code) has the most cancellations (244, -£146,784.46);
`22423` (Regency Cakestand) — also a top-5 revenue product — has 181; `POST` (postage)
has 126. `D` (Discount) has a **100% cancellation rate** (77 cancellations, 0 valid
sales) — structurally expected, since a discount adjustment line is a credit by
definition and would never be classified `valid_sale`.

## Customer behaviour

_Query: `sql/analysis/030_customer_intelligence.sql`_

- **4,372 identified customers** (`dim_customer`); **4,338** have at least one
  qualifying (`valid_sale`) purchase — the remaining 34 exist only via a cancellation
  or non-standard row and are correctly excluded from RFM/CLV (identity-and-purchase-
  dependent metrics).
- **Repeat customer rate: 65.58%** (2,845 of 4,338).
- **Spend is heavily right-skewed**: mean customer spend £1,915.74 vs. **median
  £655.34** — the mean is not a representative "typical customer" figure. P90 spend:
  £3,537.63.
- **Revenue concentration**: the top 10% of customers by spend account for **59.80%**
  of customer-attributable revenue; the bottom 10% account for 0.48%.
- Top customers by observed historical revenue (customer lifetime value **as observed
  in this dataset's window, not a predicted future value**): customer 14646
  (£279,489.02, 73 orders), 18102 (£256,438.49, 60 orders), 17450 (£187,482.17, 46
  orders).

**RFM segmentation** (`v_customer_rfm`) — a quartile-based heuristic (`NTILE(4)` on
Recency/Frequency/Monetary, then simple score thresholds), **not a validated
behavioural model**:

| Segment | Customers | Avg recency (days) | Avg frequency | Avg monetary |
|---|---|---|---|---|
| Champions | 486 | 7.6 | 15.5 | £8,818.60 |
| Loyal | 1,034 | 23.1 | 5.2 | £2,012.44 |
| At risk | 648 | 115.6 | 4.2 | £1,487.43 |
| New / occasional | 648 | 25.3 | 1.4 | £489.32 |
| Other | 1,522 | 187.2 | 1.3 | £435.51 |

(`sql/analysis/030_customer_intelligence.sql` query C8.)

**Cohort retention** (`v_customer_cohort_retention`) — the December 2010 cohort (885
customers) retains 26-50% month-to-month across the observed window, with no clear
monotonic trend. **Observation-window limitation**: cohorts formed near the dataset's
end (e.g. November 2011, 323 customers; December 2011, 41 customers) have had little
or no chance to show retention in later months, simply because those months aren't in
the data. Their absence must not be read as confirmed churn.

## Geographic performance

United Kingdom accounts for 84% of net revenue and 90% of orders — see the Sales
performance table above for the next four markets. No sub-national UK geography is
available in the source data (see `docs/data_dictionary.md`), so no regional
breakdown within the UK is possible.

## Transaction quality

_Query: `sql/analysis/040_transaction_quality.sql`_

| `transaction_status` | Rows | % of rows |
|---|---|---|
| `valid_sale` | 530,103 | 97.82% |
| `cancellation` | 9,288 | 1.71% |
| `potential_return` | 1,336 | 0.25% |
| `non_standard` | 1,182 | 0.22% |

- Cancellation rate (of valid_sale + cancellation rows): **1.72%**.
- Missing `CustomerID`: 135,080 rows overall (24.93%); within cancellations
  specifically, 383 of 9,288 (4.12%) have no `CustomerID` and so can't be attributed to
  an individual customer's RFM/CLV figures (they are still counted in organisation-wide
  net revenue).
- **Duplicate-candidate sensitivity**: removing duplicate candidates (per the
  documented "keep the first occurrence per exact-match group" rule —
  `v_valid_sales_deduplicated`) changes revenue by **-£25,125.59 (-0.24%)**, units sold
  by **-16,259 (-0.29%)**, and AOV by **-£1.26 (-0.24%)**, with **no change to order
  count**. This is a real but immaterial-scale sensitivity for headline reporting;
  neither the complete nor the deduplicated figure is asserted as "the true" number —
  see `docs/kpi_definitions.md`'s duplicate policy for why both are kept available.

## Data limitations

- Single historical snapshot (2010-12-01 to 2011-12-09), not a live feed.
- No product cost, margin, or shipping cost data — only revenue KPIs are possible.
- No customer demographics beyond country; no reliable UK sub-national geography.
- December 2011 is a partial month (9 of 31 days) — excluded from like-for-like
  monthly comparisons where noted.
- Cohort retention for cohorts formed in the last 1-3 months of the dataset is not
  comparable to earlier cohorts — insufficient observation window, not confirmed churn.
- RFM segments are a scoring heuristic, not a validated behavioural segmentation.
- 10,147 rows (2.4%) are exact-duplicate candidates, preserved rather than dropped;
  their revenue impact is small (-0.24%) but non-zero.

## Actionable business recommendations

These follow directly from the findings above — each is stated as a recommendation to
investigate or act on, not as a proven conclusion:

1. **Exclude `DOT` (postage) and other non-product stock codes from "top product"
   reporting** intended for merchandising decisions — they inflate revenue-based
   product rankings without representing demand for a sellable item.
2. **Flag single large orders before using unit-volume rankings** for inventory or
   merchandising decisions (e.g. `23843`'s #1 quantity rank is one bulk order, not
   broad demand) — the query in `sql/analysis/020_product_performance.sql` (B3) already
   surfaces these for review.
3. **Investigate the 65 products with cancellation activity** (`v_product_cancellation_activity`),
   starting with `22423` (Regency Cakestand) — a top-5 revenue product that is also
   among the most cancelled, worth checking for a quality or fulfilment issue.
4. **Treat revenue concentration (top 10% = 59.80%) as a retention priority** — losing
   a handful of top customers (e.g. the 4 customers each generating >£100k) would have
   an outsized impact; consider a dedicated account-management approach for the
   `Champions` RFM segment.
5. **Do not report December 2011 month-over-month growth without the partial-month
   caveat** — presenting -70% as a real decline would be actively misleading.
