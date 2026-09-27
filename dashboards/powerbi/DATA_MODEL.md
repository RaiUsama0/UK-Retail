# Power BI Data Model

**Status: specification + verified data exports. No `.pbix`/`.pbip` file exists.**
Power BI Desktop is installed on the build machine, but it is a GUI-only application
with no command-line or scripting surface this environment can drive, and no
screenshot/GUI-automation tool was available to verify anything rendered correctly.
Rather than hand-author a binary/project file with no way to confirm it opens
correctly in Power BI Desktop, this documents exactly what a report author needs to
build it by hand, backed by real, row-count-verified data. See `README.md` in this
folder for the exact build steps.

## Import mode, minimal table set

**9 tables imported, not all 19 warehouse views.** Product/country ranking views
(`v_product_performance`, `v_revenue_by_country`, etc.) are deliberately *not*
imported — their logic (a `GROUP BY` + `RANK()`) is simple enough to recreate as DAX
measures directly over the star schema, which also gives proper interactive
cross-filtering that a flattened, pre-aggregated view would lose. Only the star schema
itself, plus the Phase 5 views whose logic is genuinely too complex to sanely
re-derive in DAX (RFM scoring, cohort retention, the partial-month determination), are
imported as-is.

| Table (CSV) | Source | Grain | Rows (verified) |
|---|---|---|---|
| `fact_sales` | `warehouse.fact_sales` | One row per cleaned-dataset row (= one raw invoice line) | 541,909 |
| `dim_date` | `warehouse.dim_date` | One row per calendar day in the observed range | 374 |
| `dim_product` | `warehouse.dim_product` | One row per distinct `stock_code` | 4,070 |
| `dim_customer` | `warehouse.dim_customer` | One row per distinct known `customer_id` | 4,372 |
| `dim_country` | `warehouse.dim_country` | One row per distinct country | 38 |
| `v_customer_rfm` | `warehouse.v_customer_rfm` | One row per customer with >= 1 qualifying purchase | 4,338 |
| `v_customer_cohort_retention` | `warehouse.v_customer_cohort_retention` | One row per (cohort_month, activity_month) pair | 91 |
| `v_monthly_revenue_growth` | `warehouse.v_monthly_revenue_growth` | One row per calendar month | 13 |
| `v_duplicate_sensitivity` | `warehouse.v_duplicate_sensitivity` | One row per dataset version (complete / deduplicated) | 2 |

Row counts above were re-verified against the live PostgreSQL instance at export time
(`ingest-data export-powerbi` re-counts every source and compares — see
`reports/` for the run log). CSVs live in `dashboards/powerbi/data/` (gitignored,
regenerate with `ingest-data export-powerbi`).

## Relationships

```
dim_date (1) ────────────< (many) fact_sales
dim_product (1) ─────────< (many) fact_sales
dim_country (1) ──────────< (many) fact_sales
dim_customer (1) ─────────< (many) fact_sales      [fact_sales.customer_key is NULLABLE —
                                                     24.93% of rows have no match; Power BI
                                                     treats these as blank, not an error]
dim_customer (1) ─────────── (1) v_customer_rfm     [one-to-one, on customer_key]

v_customer_cohort_retention   — STANDALONE, no relationship to the star schema
v_monthly_revenue_growth      — STANDALONE, no relationship to the star schema
v_duplicate_sensitivity       — STANDALONE, no relationship to anything
```

**Why three tables are deliberately disconnected** (preventing double-counting, per
the brief): `v_customer_cohort_retention` and `v_monthly_revenue_growth` are already
fully pre-aggregated (to month, or to cohort x activity-month grain). Relating either
to `fact_sales` or to `dim_date` would either be structurally wrong (a month-grain
table naively related to a day-grain `dim_date` on a month key creates a many-to-many
relationship prone to silent double-counting the moment two visuals share the same
table) or simply unnecessary (nothing needs to cross-filter between per-transaction
fact rows and an already-monthly-aggregated total). Both are used as standalone
sources for their own dedicated visuals (the monthly trend chart; the cohort heatmap)
and never mixed into a visual alongside `fact_sales`-sourced measures.

`v_customer_rfm` is the one exception that *is* related (one-to-one on `customer_key`)
so it can be used as a slicer/filter context for `fact_sales`-based visuals (e.g.
"show revenue trend filtered to the Champions segment"). Because it's one-to-one, this
cannot inflate `fact_sales` row counts — but its own `monetary` column (a
pre-aggregated per-customer total) must never be re-summed inside a visual that is
also summing `fact_sales[line_revenue]` directly; use one measure or the other, not
both, in the same visual. This is called out again in `DAX_MEASURES.md`.

`dim_date` is marked as the model's official Date table in Power BI (Model view ->
`dim_date` -> Mark as date table -> `date_value`).

## Preventing double-counting: the core rule

Every DAX measure that touches `fact_sales` filters `transaction_status` explicitly
(`valid_sale` for ordinary sales KPIs, or an explicit combination for revenue nets —
see `DAX_MEASURES.md`). Never `SUM(fact_sales[line_revenue])` unfiltered — that would
silently include `potential_return` and `non_standard` rows in a "sales" total. This
mirrors the SQL convention established in Phase 5 exactly (`docs/kpi_definitions.md`).

## Column-level notes for import

- `fact_sales.transaction_status` imports as text (the Postgres ENUM serialises to its
  label in the CSV) — fine for `CALCULATE(..., fact_sales[transaction_status] =
  "valid_sale")` filters.
- `fact_sales.flag_*` columns import as `TRUE`/`FALSE` text from CSV — Power BI's CSV
  import correctly infers these as a Boolean column type; verify this in Power Query
  before loading (the "Data Type" for each `flag_*` column should read "True/False",
  not "Text").
- `dim_customer` and `dim_product` have **no** free-text description columns beyond
  `dim_product.description` — no personal customer data beyond a numeric
  `customer_id` is present anywhere in this model (see the Streamlit-equivalent
  privacy note in `docs/architecture/overview.md`).
