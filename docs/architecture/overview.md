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
database.py       -> (Phase 4) loads a star schema into PostgreSQL:
                       fact_sales, dim_product, dim_customer, dim_date, dim_country
        │
        ▼
sql/analysis/*.sql -> KPI queries (aggregations, CTEs, window functions),
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

## Database design

A star schema, chosen over a single flat table so that:
- Dimension attributes (product description, customer, calendar, country) aren't
  repeated on every fact row.
- SQL analysis (Phase 5) can demonstrate realistic join patterns (fact-to-dimension),
  which is what the target junior roles actually do day to day.

Grain of `fact_sales`: one row per original invoice line, keyed by the `source_row_id`
already established in Phase 3 (documented in `sql/schema/` once implemented in Phase 4)
so the load is idempotent and repeatable.

Monetary columns use `NUMERIC(12,2)`, never floating point, to avoid rounding errors in
aggregated revenue figures.

## Testing strategy

- Unit tests for ingestion, cleaning, validation, and profiling, using small synthetic
  fixtures with known, hand-computed expected outputs (implemented Phases 2-3; 36
  tests as of Phase 3 — `pytest`). Further KPI/database/dashboard tests land in
  Phase 8 as those modules are built.
- Data quality tests: required fields, types, valid quantity/price rules, date parsing,
  transaction classification, decimal-safe revenue, and reconciliation between raw and
  cleaned row counts — enforced as fatal regression guards in `validation.py`.
- CI (`.github/workflows/ci.yml`) runs lint (`ruff`) and `pytest` on every push/PR
  without requiring any private credentials.

## Dashboard requirements

- **Power BI** — the primary dashboard (Executive Overview, Product & Sales
  Performance, Customer Intelligence pages), connected directly to PostgreSQL.
- **Streamlit** — an optional public demo, reading the same validated data, with no
  database credentials or personal customer identifiers exposed.

## Deliverables and acceptance criteria

Tracked per-phase in each phase's own summary; the overall project is complete when:
reproducible pipeline runs end to end, PostgreSQL schema is loaded and validated, SQL
KPIs reconcile with Python, Power BI model + DAX are documented (PBIX finished manually
if Power BI Desktop isn't available in this environment), tests and CI pass, and the
README/business case study are written from real, verified results only.
