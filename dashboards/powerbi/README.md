# Power BI Dashboard — Implementation Status

**No `.pbix` or `.pbip` file exists in this repository.**

Power BI Desktop is installed on the machine this project was built on, but it is a
GUI-only application with no command-line or scripting interface, and this
environment has no screenshot or GUI-automation capability to drive it or verify what
it renders. Hand-authoring a binary `.pbix` or a text-based `.pbip`/TMDL project with
no way to confirm it actually opens correctly in Power BI Desktop would risk handing
over a file that looks complete but is silently corrupt — worse than clearly
documenting what a report author needs to build by hand. So instead, this folder
contains everything needed to build the real thing quickly and correctly:

| File | What it is |
|---|---|
| `DATA_MODEL.md` | The 9 tables to import, their grain, and every relationship (with the reasoning for which tables are deliberately *not* related, to prevent double-counting) |
| `DAX_MEASURES.md` | Every required measure, with the exact expected value from the equivalent, already-verified SQL query |
| `PAGE_SPECIFICATIONS.md` | Visual-by-visual layout for all 4 dashboard pages, including the required partial-month warning and data-quality captions |
| `data/*.csv` | The actual import data, exported from the live PostgreSQL warehouse and row-count-verified against it (see below) |

## The data is real and verified

```bash
ingest-data export-powerbi
```

exports all 9 tables to `data/*.csv` (gitignored — regenerate rather than commit; a
541,909-row CSV doesn't belong in version control) and re-counts every source live in
PostgreSQL to confirm each export matches exactly. Last verified run: all 9/9 exports
matched (`fact_sales` 541,909 rows; `dim_product` 4,070; `dim_customer` 4,372;
`dim_country` 38; `dim_date` 374; `v_customer_rfm` 4,338; `v_customer_cohort_retention`
91; `v_monthly_revenue_growth` 13; `v_duplicate_sensitivity` 2).

## Building the report (manual, in Power BI Desktop)

1. Open Power BI Desktop -> **Get Data -> Text/CSV**, import each file in `data/`.
   Alternatively, for a live connection instead of a static import, use **Get Data ->
   PostgreSQL** with the same host/port/database/credentials as `.env`, and select the
   9 tables/views listed in `DATA_MODEL.md` directly.
2. In **Model view**, create the relationships exactly as specified in
   `DATA_MODEL.md` — pay particular attention to which tables are deliberately left
   **unrelated**.
3. Mark `dim_date` as the official Date table (`date_value` column).
4. Create a measures table (`_Measures`) and add every measure from
   `DAX_MEASURES.md`.
5. Build the 4 pages per `PAGE_SPECIFICATIONS.md`.
6. **Reconcile**: drop each measure onto a blank card with no filters and compare
   against the "Expected (unfiltered)" value listed next to it in `DAX_MEASURES.md`.
   If anything disagrees, the model has an error — the SQL-side figures are already
   independently verified (`tests/test_analysis.py`, run against a live database).

## Refreshing the report from PostgreSQL

- **Import mode (the CSVs)**: re-run `ingest-data export-powerbi` after any upstream
  pipeline change, then in Power BI Desktop use **Home -> Refresh** (it re-reads the
  same CSV paths).
- **Direct PostgreSQL connection**: **Home -> Refresh** re-runs the same queries
  against whatever is currently loaded in the warehouse.
- **Either way, this is a static historical dataset (2010-12-01 to 2011-12-09), not a
  live feed.** A refresh re-reads the same historical data — it does not fetch new
  transactions. State this explicitly on the dashboard itself (see
  `PAGE_SPECIFICATIONS.md`'s reporting-period caption) so it is never mistaken for a
  live operational dashboard.

## What's implemented vs. what needs manual work

| | Status |
|---|---|
| Data model design (tables, grain, relationships) | **Documented, and the underlying data verified** |
| DAX measure definitions | **Documented, with SQL-reconciled expected values** |
| Page/visual layout | **Documented in full detail** |
| Actual `.pbix`/`.pbip` file | **Not created** — requires manual work in Power BI Desktop following the above |
| Screenshots | **None** — no report exists yet to screenshot |
