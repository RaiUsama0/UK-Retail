# Dashboard User Guide

Written for whoever uses the finished report once it's built from
`PAGE_SPECIFICATIONS.md` — a stakeholder, an interviewer, or a portfolio site visitor.

## What this dashboard is

An analysis of **historical** UK e-commerce transactions covering **2010-12-01 to
2011-12-09** (the UCI "Online Retail" dataset). It is a completed, static snapshot —
refreshing it re-reads the same historical data; it does not fetch new transactions.
Nothing on this dashboard represents live or current business activity.

## Pages

1. **Executive Overview** — the headline numbers (net revenue, orders, AOV, active
   customers) and the monthly trend. Start here.
2. **Product and Sales Performance** — which products drive revenue vs. volume, and
   two important caveats: the top "product" by revenue is actually a postage charge,
   and the top product by quantity is dominated by one large bulk order.
3. **Customer Intelligence** — who the customers are, how concentrated spend is among
   them, and an RFM segmentation. The RFM segments are a scoring heuristic (quartile
   thresholds), not a scientifically validated customer typology — use them as a
   starting point for investigation, not a final answer.
4. **Transaction Quality and Data Reliability** — how much of the data is an ordinary
   sale vs. a cancellation, a potential return, or something non-standard, and what
   that means for trusting any given number.

## Reading the KPI cards

- **Net revenue** = gross sales revenue, less the value of cancelled orders.
  Cancellations are real (a customer really did cancel), so they're netted off — this
  is not the same as "gross bookings."
- **Potential returns** are *not* the same as confirmed refunds. In this dataset every
  potential-return row has £0 value, so they carry no monetary weight in net revenue —
  they're reported for transparency, not because a refund was issued.
- **Duplicate-candidate records** are preserved in every headline figure by default. A
  separate comparison view shows what the numbers would look like with them removed —
  neither version is asserted as "the real" number; see Page 4's caption for why.

## Filters

- **Date range** (Pages 1-2): drag to any period. **Watch for the partial-month
  warning** — if your selection includes December 2011, a banner will appear because
  that month's data stops on the 9th. A month-over-month % that includes it is not a
  fair comparison to a full month.
- **Country** (Pages 1-2): the United Kingdom dominates by volume; use the slicer to
  isolate other markets if the UK's scale makes smaller bars hard to read.
- **RFM segment** (Page 3): filters the whole page to customers in that heuristic
  segment.

## What this dashboard cannot tell you

- No product cost or margin data exists in the source — every revenue figure is gross
  or net *sales* revenue, never profit.
- No customer demographics beyond country.
- No UK sub-national/regional geography.
- "Customer lifetime value" here means revenue actually observed within this dataset's
  window — it is not a predicted future value from a churn or survival model.
- Cohort retention for customers acquired in the last 1-2 months of the dataset isn't
  comparable to earlier cohorts — the dataset simply ends too soon after they were
  acquired to show later-month retention; that is not the same as those customers
  having churned.
