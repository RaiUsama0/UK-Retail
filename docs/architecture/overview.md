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
ingestion.py      -> data/raw/ (frozen copy, immutable) + profiling report + logs
        │
        ▼
cleaning.py +
validation.py     -> classifies every row as sale / cancellation / return / questionable
                     (Pandera schemas enforce types and value rules)
        │
        ▼
data/processed/   -> validated, typed dataset + cleaning report (before/after counts)
        │
        ▼
database.py       -> loads a star schema into PostgreSQL:
                       fact_sales, dim_product, dim_customer, dim_date, dim_country
        │
        ▼
sql/analysis/*.sql -> KPI queries (aggregations, CTEs, window functions),
                       reconciled against independently computed Python results
        │
        ├──► Power BI      (SQL views + DAX measures; see dashboards/powerbi/)
        └──► Streamlit demo (dashboards/streamlit/)
```

## Database design

A star schema, chosen over a single flat table so that:
- Dimension attributes (product description, customer, calendar, country) aren't
  repeated on every fact row.
- SQL analysis (Phase 5) can demonstrate realistic join patterns (fact-to-dimension),
  which is what the target junior roles actually do day to day.

Grain of `fact_sales`: one row per original invoice line. Since the raw data has no
native line-level identifier, a deterministic surrogate key is generated (documented in
`sql/schema/` once implemented in Phase 4) so the load is idempotent and repeatable.

Monetary columns use `NUMERIC(12,2)`, never floating point, to avoid rounding errors in
aggregated revenue figures.

## Testing strategy

- Unit tests for ingestion, cleaning, validation, and KPI calculations, using small
  synthetic fixtures with known, hand-computed expected outputs (Phase 8).
- Data quality tests: required fields, types, valid quantity/price rules, date parsing,
  and reconciliation between raw and cleaned row counts.
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
