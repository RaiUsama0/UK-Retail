# Architecture Overview

## Business objectives

Give a UK online retailer (represented by the historical Online Retail dataset)
visibility into revenue trends, product performance, geographic sales mix, order
economics, customer repeat behaviour, and cancellation/return impact — via a
reproducible pipeline and a set of dashboards, in a way a junior analyst/engineer can
build, test, and explain end to end.

## Data source and limitations

See `docs/data_dictionary.md` for the full column-level breakdown. In summary: a
historical (non-live) transactional export, UK-dominated, with no cost, margin,
shipping, demographic, or reliable sub-national regional data. All documentation and
dashboards state this explicitly rather than implying real-time or enriched data.

## System architecture

```
Online Retail.xlsx (pinned source, gitignored)
        │
        ▼
ingestion.py      -> data/raw/ (checksum-verified immutable copy) + logs
        │
        ▼
profiling.py      -> reports/data_profile.{json,md} — every statistic computed from
                     the actual data, no rows removed or modified
        │
        ▼
validation.py     -> raw-data schema validation (Pandera; fatal on structural failure)
                     + business-rule warnings (non-fatal: negative qty, cancellations,
                     missing CustomerID, etc. — real business events, not defects) +
                     post-cleaning invariant checks (fatal regression guards: row
                     count preserved, every row classified, line_revenue consistent)
        │
        ▼
cleaning.py       -> classifies every row's transaction_status (valid_sale /
                     cancellation / potential_return / non_standard) with a documented
                     precedence, adds non-exclusive business-rule flags, computes
                     decimal-safe line_revenue — never adds/removes/reorders rows
        │
        ▼
data/processed/   -> online_retail_cleaned.parquet (typed, classified, analysis-ready)
                     + reports/cleaning_summary.{json,md} (real counts, reconciled)
        │
        ▼
warehouse.py      -> loads a PostgreSQL star schema (sql/schema/, sql/transformations/):
                     staging.stg_cleaned_sales -> warehouse.dim_* -> warehouse.fact_sales,
                     all in one transaction, upserted idempotently, then reconciled
                     against the source dataframe
                     + reports/warehouse_load_report.{json,md}
        │
        ▼
sql/analysis/*.sql -> (Phase 5) KPI queries (aggregations, CTEs, window functions),
                       reconciled against independently computed Python results
        │
        ├──► Power BI      (SQL views + DAX measures; see dashboards/powerbi/)
        └──► Streamlit demo (dashboards/streamlit/)
```

## Cleaning strategy (Phase 3 — implemented)

Full detail and verified figures: `docs/kpi_definitions.md` (classification precedence,
revenue formulas) and `docs/data_dictionary.md` (cleaned schema, real counts). In brief:

- **Nothing is deleted.** Every raw row maps to exactly one cleaned row. Ambiguous
  records (negative quantity, non-positive price, duplicates, anomalous formats) are
  *classified and flagged*, not dropped or silently reinterpreted.
- **`transaction_status`** is a single, precedence-ordered classification
  (`cancellation` > `potential_return` > `non_standard` > `valid_sale`); a wide set of
  independent boolean flags captures everything else (missing identifiers,
  duplicate-candidate, non-standard stock code, etc.) without collapsing information
  into one broad category.
- **`source_row_id`** (0-based raw file position) is a *technical* identifier, not a
  business transaction ID — the raw data has none at the line-item grain. Phase 4 will
  extend this into the `fact_sales` surrogate key.
- **Revenue** is computed via Python `Decimal`, not raw float64, specifically to avoid
  summation drift when aggregating 540k+ rows for the cleaning report's reconciliation
  totals.
- Passing these checks confirms internal consistency, not that every field was
  correctly recorded at the source — see the limitations note in `data_dictionary.md`.

## Database design (Phase 4 — implemented)

A star schema, chosen over a single flat table so that:
- Dimension attributes (product description, customer, calendar, country) aren't
  repeated on every fact row.
- SQL analysis (Phase 5) can demonstrate realistic join patterns (fact-to-dimension),
  which is what the target junior roles actually do day to day.

### Entity-relationship diagram

```
                    ┌───────────────────┐
                    │   dim_date        │
                    │ date_key (PK)     │
                    │ date_value        │
                    │ year/quarter/...  │
                    └─────────▲─────────┘
                              │
┌───────────────────┐        │        ┌───────────────────┐
│   dim_product      │        │        │   dim_country      │
│ product_key (PK)   │        │        │ country_key (PK)   │
│ stock_code (UNIQUE) │        │        │ country_name (UNQ) │
│ description         │        │        └─────────▲─────────┘
│ description_variant │        │                  │
│   _count             │        │                  │
└─────────▲───────────┘        │                  │
          │                    │                  │
          │        ┌───────────┴──────────┐        │
          └────────┤     fact_sales       ├────────┘
                    │ source_row_id (PK)  │
                    │ invoice_no          │
                    │ product_key (FK)    │◄── NOT NULL (every row has a product)
                    │ customer_key (FK)   │◄── NULLABLE (24.93% of rows have no customer)
                    │ country_key (FK)    │◄── NOT NULL
                    │ date_key (FK)       │◄── NOT NULL
                    │ invoice_timestamp   │
                    │ quantity            │
                    │ unit_price          │
                    │ line_revenue        │
                    │ transaction_status  │
                    │ flag_* (x7)         │
                    └──────────▲──────────┘
                               │
                    ┌──────────┴──────────┐
                    │   dim_customer      │
                    │ customer_key (PK)   │
                    │ customer_id (UNQ)   │  -- no country column: see note below
                    └─────────────────────┘
```

### Grain and identifier separation

`fact_sales` grain: **one row per Phase 3 cleaned-dataset row** (= one row per original
raw invoice line). Primary key is `source_row_id`, **reused directly** from Phase 3 —
not a second, redundant surrogate key. `invoice_no` (the real business identifier) is
kept as its own column, separate from that technical primary key, per the project's
identifier-separation convention (also applied in every dimension: `product_key` vs
`stock_code`, `customer_key` vs `customer_id`).

All 541,909 cleaned rows are loaded into `fact_sales`, including duplicate-candidate
rows, cancellations, potential returns, and non-standard transactions — the fact table
is never pre-filtered; analytical views (below) provide filtered/aggregated
perspectives on top of it.

### Two data-quality-driven design decisions

Both came from actually querying the cleaned dataset before writing DDL, not from
assuming a "normal" star schema shape:

- **`dim_customer` has no country column.** Inspection showed 8 of 4,372 customers
  (0.18%) transacted from more than one country — so country is not a stable customer
  attribute in this dataset. Country is modelled only as its own dimension, joined
  directly from `fact_sales`.
- **`dim_product.description` is a MODE, not an assumed-unique value.** 647 of 4,070
  stock codes have more than one distinct non-null description in the source data
  (often a genuine description alongside an inventory annotation like `"damaged"` or
  `"check"`). The load computes `MODE() WITHIN GROUP (ORDER BY description)` per
  `stock_code` and records `description_variant_count` so the ambiguity is visible,
  not hidden.

### Idempotency strategy

**Upsert, not truncate-and-replace-everything, and not application-level "check first"
logic.** `staging.stg_cleaned_sales` is truncated and bulk-loaded via `COPY` on every
run (it's a transient landing zone, not the source of truth). Dimensions and
`fact_sales` are populated with `INSERT ... ON CONFLICT (<business or technical key>)
DO UPDATE` / `DO NOTHING` — the database's own primary/unique key constraints are what
prevent duplicates, not a Python-side existence check. Re-running the loader against
identical source data is a true no-op: verified by loading the real dataset twice in a
row and confirming `fact_sales` still has exactly 541,909 rows both times (see
`reports/warehouse_load_report.md` and `tests/test_warehouse_integration.py::test_load_warehouse_is_idempotent`).

The whole load — staging truncate, `COPY`, dimension upserts, fact upsert — runs in a
**single database transaction**, so a failure anywhere rolls back everything. Verified
directly: a deliberately broken load (a null `transaction_status`) was rejected by a
`NOT NULL` constraint, the transaction rolled back, and `fact_sales` was confirmed
unchanged (`tests/test_warehouse_integration.py::test_load_warehouse_rolls_back_on_failure`).

### If a second data source or ingestion batch were introduced

This design assumes a single source and a full-refresh load pattern (the whole cleaned
dataset is reloaded every run). That assumption is baked into using `source_row_id`
directly as `fact_sales`' primary key — it's only unique because it's a raw-file row
position for *one* file. Extending to multiple sources/batches would require:

1. A composite or namespaced key instead — e.g. `(source_system, batch_id,
   source_row_id)` as the natural key, with a genuine `SERIAL`/`IDENTITY` surrogate key
   introduced on `fact_sales` for the first time (currently avoided deliberately, per
   the single-source design).
2. An explicit `dim_source` or `batch` tracking table recording when each batch was
   loaded, from where, and its row count — for auditability across batches.
3. Switching the fact load from "upsert the whole dataset" to "append new batches,
   upsert only rows belonging to the current batch" — otherwise a second source's rows
   could collide with or be silently overwritten by the first's.
4. Revisiting `dim_customer`/`dim_product` uniqueness: a `customer_id` or `stock_code`
   is only guaranteed unique *within* this one dataset; a second source might reuse the
   same codes for different real-world entities, which would need a per-source
   namespace on the dimension's business key too.

Monetary columns use `NUMERIC(12,4)` (`unit_price` — the source data has up to 3
decimal places) and `NUMERIC(14,2)` (`line_revenue`), never floating point, to avoid
rounding errors in aggregated revenue figures.

### Indexing — measured, not assumed

Indexes on `fact_sales`: `date_key`, `customer_key`, `product_key`, `invoice_no`,
`transaction_status` (`sql/schema/005_indexes.sql`). Measured with `EXPLAIN ANALYZE`
against the real, fully-loaded 541,909-row table:

| Query | Plan used | Time |
|---|---|---|
| Lookup by `invoice_no` | Index Scan (`idx_fact_sales_invoice_no`) | 0.05 ms |
| Lookup by `customer_key` | Bitmap Index Scan (`idx_fact_sales_customer_key`) | 0.39 ms |
| Filter `transaction_status = 'potential_return'` (0.25% of rows — selective) | Index Scan (`idx_fact_sales_transaction_status`) | 1.7 ms |
| Monthly revenue (`GROUP BY` year/month, filtered to `valid_sale` = 97.8% of rows) | Parallel Sequential Scan (index *not* used) | 90 ms |
| Top-10 products by revenue (`GROUP BY product_key`, `valid_sale` filter) | Parallel Sequential Scan | 72 ms |

The `transaction_status` index is used exactly where the query planner should use
it — a highly selective filter (`potential_return`, `non_standard`, ~0.2-0.25% of
rows each) — and correctly *ignored* in favour of a sequential scan when the filter
matches ~98% of rows (`valid_sale`), since scanning the whole table is cheaper than a
huge index lookup. This is the query planner behaving correctly, not a missing index.

## Analytical layer (Phase 5 — implemented)

Full KPI definitions: `docs/kpi_definitions.md`. Real findings: `docs/business_insights.md`.
SQL: `sql/schema/007_phase5_views.sql` (10 new views) + `sql/analysis/*.sql` (33
illustrative, standalone queries across sales/product/customer/quality analysis,
organised by business area).

**Analytical convention**: every view reads from the complete `fact_sales` table (or
`v_valid_sales`), never a pre-filtered copy. `v_valid_sales_deduplicated` exists only
for explicitly-labelled sensitivity analysis (`v_duplicate_sensitivity[_delta]`) — it
is never the default source for a headline KPI.

**A performance issue found and fixed by measurement, not assumption**:
`v_duplicate_sensitivity_delta`'s first draft used four correlated scalar subqueries,
each independently re-evaluating `v_valid_sales_deduplicated`'s window-function
deduplication pass over 530k+ rows. `EXPLAIN ANALYZE` measured this at **3,438 ms**.
Rewriting it as a single scan with conditional (`FILTER`) aggregation — computing the
underlying view exactly once instead of four times — measured at **890 ms**, a 3.9x
improvement, with identical output. No new index or materialised view was introduced;
the fix was the query itself. All other new views run in 270-965 ms against the full
541,909-row table — acceptable for a BI dashboard refresh, not optimised further
without a demonstrated need.

**Reconciliation**: `tests/test_analysis.py` (12 tests) loads a small hand-computed
synthetic dataset through the real Phase 3/4 pipeline and asserts the SQL views
produce exactly the expected monthly totals, product revenue, RFM scores, cohort
counts, and duplicate-sensitivity deltas — run against a real, live PostgreSQL
instance, not mocked.

## Testing strategy

- Unit tests for ingestion, cleaning, validation, profiling, and the warehouse loader's
  pure-Python helpers, using small synthetic fixtures with known, hand-computed
  expected outputs (implemented Phases 2-5; 66 tests as of Phase 5 — `pytest`).
- Data quality tests: required fields, types, valid quantity/price rules, date parsing,
  transaction classification, decimal-safe revenue, and reconciliation between raw and
  cleaned row counts — enforced as fatal regression guards in `validation.py`.
- **Database integration tests** (`tests/test_warehouse_integration.py`, 12 tests;
  `tests/test_analysis.py`, 12 tests): schema creation, idempotent DDL, row-count/
  duplicate/status/monetary-precision preservation, nullable customer FK, idempotent
  reload, transactional rollback on failure, warehouse reconciliation, and — for the
  analytical layer — monthly-total, product-revenue, RFM-score, cohort-count, and
  duplicate-sensitivity reconciliation against hand-computed expected values. Run
  against a dedicated `<database>_test` database, auto-created on first run — never
  the real development database. Automatically **skipped** (not failed) if PostgreSQL
  isn't reachable, so the credential-free CI workflow stays functional either way.
- CI (`.github/workflows/ci.yml`) runs lint (`ruff`) and `pytest` on every push/PR,
  with a PostgreSQL 16 service container so the database integration tests run for
  real in CI too, not just locally.

## Dashboard requirements

- **Power BI** — the primary dashboard (Executive Overview, Product & Sales
  Performance, Customer Intelligence pages), connected directly to PostgreSQL.
- **Streamlit** — an optional public demo, reading the same validated data, with no
  database credentials or personal customer identifiers exposed.

## Power BI implementation specification (Phase 6 — not yet built)

**No PBIX file or dashboard exists yet.** This is a specification for Phase 6, written
against the actual views that now exist, not a description of finished work.

### Dashboard pages and their datasets

| Page | Primary view(s) | Grain |
|---|---|---|
| Executive Overview | `v_monthly_revenue_growth`, headline totals (`sql/analysis/010`) | One row per month |
| Monthly Sales Trends | `v_monthly_revenue_growth` | One row per month |
| Product Performance | `v_product_performance`, `v_product_monthly_trend`, `v_product_cancellation_activity` | One row per product (+ per product-month for the trend) |
| Country Performance | `v_revenue_by_country`, `v_product_country_rankings` | One row per country (+ per country-product) |
| Customer Analysis | `v_customer_rfm`, `v_customer_summary` (Phase 4) | One row per identified customer |
| RFM Segmentation | `v_customer_rfm` | One row per identified customer with >=1 valid_sale |
| Cohort Retention | `v_customer_cohort_retention` | One row per (cohort_month, activity_month) pair |
| Transaction Quality | `v_data_quality_monitor` (Phase 4), `v_duplicate_sensitivity[_delta]` | One row per transaction_status |

### Data relationships (Power BI model view)

Import `warehouse.dim_date`, `dim_product`, `dim_customer`, `dim_country`, and
`fact_sales` directly (star schema, exactly as modelled in PostgreSQL — see the ER
diagram above) for interactive cross-filtering; import the Phase 5 views as
independent, pre-aggregated tables (they don't need further relationships to the star
schema — each is already a finished analytical grain). Mark `dim_date` as Power BI's
official Date table.

### KPI definitions

Reuse `docs/kpi_definitions.md` verbatim as the measure specification — every DAX
measure below is a direct translation of an already-implemented, already-verified SQL
definition, not a new one invented for Power BI.

### Recommended visualisations

- Executive Overview: KPI cards (net revenue, orders, AOV, active customers), a line
  chart of `v_monthly_revenue_growth` with `is_partial_month` visually distinguished
  (e.g. a dashed/greyed final point), a country map or bar chart.
- Product Performance: a table of `v_product_performance` with conditional formatting
  on `pct_of_total_revenue`; a note/tooltip flagging non-product stock codes.
- RFM Segmentation: a scatter plot (Recency x Frequency, sized by Monetary, coloured
  by `rfm_segment_heuristic`) — labelled as a heuristic in the page title, not "Customer
  Segments" unqualified.
- Cohort Retention: a heatmap (`cohort_month` x `month_index`, coloured by
  `retention_pct`), with `dataset_last_month` used to grey out cells with insufficient
  observation window rather than showing them as low retention.

### Required DAX measures (translating already-implemented SQL, not new logic)

```
Net Revenue = SUM(fact_sales[line_revenue])  -- filtered by transaction_status in ('valid_sale','cancellation')
Gross Sales Revenue = CALCULATE(SUM(fact_sales[line_revenue]), fact_sales[transaction_status] = "valid_sale")
Order Count = CALCULATE(DISTINCTCOUNT(fact_sales[invoice_no]), fact_sales[transaction_status] = "valid_sale")
Average Order Value = DIVIDE([Net Revenue], [Order Count])
MoM Growth % = DIVIDE([Net Revenue] - [Net Revenue (PM)], [Net Revenue (PM)])
```

### Filters and slicers

`dim_date` (month/quarter/year), `dim_country`, `transaction_status`, and an explicit
`is_partial_month` slicer/warning banner on any time-series page — Phase 5 found a
genuine -70% MoM figure driven entirely by a truncated month; the dashboard must not
let a viewer misread that the same way.

### Data refresh considerations

Source data is a static historical export — there is no live refresh source. A
Power BI refresh re-runs the same warehouse queries against whatever is currently
loaded in PostgreSQL (i.e., refreshing re-reads the same historical data, it does not
fetch new transactions). Document this explicitly on the dashboard itself so it is
never mistaken for a live operational dashboard.

## Deliverables and acceptance criteria

Tracked per-phase in each phase's own summary; the overall project is complete when:
reproducible pipeline runs end to end, PostgreSQL schema is loaded and validated, SQL
KPIs reconcile with Python, Power BI model + DAX are documented (PBIX finished manually
if Power BI Desktop isn't available in this environment), tests and CI pass, and the
README/business case study are written from real, verified results only.
