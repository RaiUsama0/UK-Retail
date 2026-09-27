# Case Study: UK E-commerce Sales & Customer Intelligence Platform

## The business problem

A UK-based online gift retailer needs to understand its own sales history: how
revenue moves month to month, which products actually drive it, who its customers
are, and how much of its raw transaction data can be trusted at face value. The
retailer's own export (the UCI "Online Retail" dataset, ~542,000 transaction lines
covering December 2010 to December 2011) is typical of real operational data: messy,
inconsistent, and full of edge cases that a naive analysis would get wrong.

The goal of this project was to build the whole path from that raw export to a
business-ready dashboard — properly, the way it would be done on a real data team —
and to be honest at every step about what the data can and can't actually support.

## Technical approach

**Pipeline**: Python ingestion (checksum-verified, so the source file is provably
untouched) → a cleaning stage that classifies every transaction line rather than
deleting anything ambiguous → a PostgreSQL star schema, loaded idempotently → a SQL
analytical layer → a Power BI-ready data model.

**Why classify instead of clean-by-deletion**: the raw data mixes ordinary sales with
cancellations, ambiguous negative-quantity rows, and a handful of clearly anomalous
manual entries. Deleting any of these would silently distort every downstream KPI.
Instead, every row keeps its original identity, is assigned exactly one status
(`valid_sale`, `cancellation`, `potential_return`, or `non_standard`) by a documented,
tested rule, and carries a set of independent flags (missing customer ID, duplicate
candidate, non-standard product code, etc.) that can coexist with any status. Nothing
is lost.

**Database**: a PostgreSQL star schema (`fact_sales` plus `dim_product`,
`dim_customer`, `dim_country`, `dim_date`), loaded with idempotent upserts inside a
single transaction — running the load twice never creates duplicate rows, and a
deliberately broken load was verified to roll back cleanly, leaving the warehouse
untouched.

**Analysis**: 19 SQL views implement everything from monthly revenue growth to RFM
customer segmentation to cohort retention — using window functions, conditional
aggregation, and CTEs rather than pulling raw data into Python for calculations that
SQL already does well. A genuine performance issue (one view taking 3.4 seconds) was
found with `EXPLAIN ANALYZE` and fixed by rewriting the query, not by adding an index
that wasn't needed.

**Dashboard**: a Power BI data model and full page-by-page specification, built on a
deliberately minimal 9-table import (not all 19 available views) to keep the model
clean and avoid double-counting when combining transaction-level facts with
pre-aggregated views.

## What the dashboard would show (once built)

Four pages: an executive overview (net revenue, orders, monthly trend, top
products/countries); product performance (with two known distortions — a shipping
charge that tops the revenue ranking, and a single bulk order that tops the quantity
ranking — surfaced rather than hidden); customer intelligence (RFM segmentation,
cohort retention, revenue concentration); and a dedicated transaction-quality page,
because "how much can I trust this number" deserves to be a first-class part of the
dashboard, not a footnote.

## Key findings

- **Net revenue: £9,758,809.99** across 19,959 orders (average order value £488.94),
  heavily UK-concentrated (84% of net revenue).
- **65.58%** of identified customers are repeat buyers; the **top 10%** of customers
  by spend account for **59.80%** of customer-attributable revenue — a strongly
  concentrated customer base.
- **December 2011 is a genuinely partial month** in the data (it ends the 9th) — its
  apparent -70% revenue "decline" is a truncation artefact, not a real trend. Getting
  this right required checking the data directly rather than assuming which end of a
  date range is "obviously" incomplete (the other edge, December 2010, looked similar
  at first glance but turned out to be a normal holiday-period gap, not a data
  boundary).
- Two rankings needed a caveat before they could be trusted: the highest-revenue
  "product" is a postage charge, and the highest-quantity product owes almost all its
  volume to one bulk order.

## Limitations, stated plainly

This is a historical snapshot, not a live feed — nothing here represents current
business activity. There's no product cost or margin data, so every figure is revenue,
never profit. RFM segments are a scoring heuristic, not a validated behavioural model.
Cohort retention for customers acquired near the end of the dataset can't be compared
fairly to earlier cohorts — the observation window simply ends too soon. And a small
share of rows (about 2.4%) are exact-duplicate candidates, non-standard transactions,
or otherwise flagged — they're kept visible rather than smoothed away.

## What I'd highlight in an interview

That the interesting engineering decisions in this project came from actually
querying the data before designing anything — discovering that 647 product codes have
more than one description, that 8 customers appear under more than one country, that
a "top product" was really a shipping line — rather than assuming a textbook schema
would fit. And that when I found a real performance problem, the fix was a better
query, not a reflexive new index.
