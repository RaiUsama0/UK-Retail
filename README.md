# UK E-commerce Sales & Customer Intelligence Platform

An end-to-end analytics pipeline — ingestion, validated cleaning, a PostgreSQL star
schema, SQL business analysis, and dashboards — built on the UCI **Online Retail**
dataset, a historical (non-live) export of transactions from a UK-based online gift
retailer covering 2010-12-01 to 2011-12-09.

> **Status:** Phase 6 (Power BI dashboard specification & verified data export)
> complete — see the note below on why no `.pbix` file exists yet. See
> [docs/architecture/overview.md](docs/architecture/overview.md) for the full plan and
> current phase-by-phase progress.

## Business problem

The retailer needs visibility into revenue trends, product performance, geographic
sales mix, order economics, customer repeat behaviour, and the impact of cancellations
— from raw transactional exports, in a reproducible and testable way.

## Dataset

- **Source:** [UCI Online Retail dataset](https://archive.ics.uci.edu/dataset/352/online+retail)
- Historical export, not a live feed. Full column-level documentation, verified data
  quality findings, and known limitations: [docs/data_dictionary.md](docs/data_dictionary.md).
- The dataset is **not** committed to this repository (see `.gitignore`). Place
  `Online Retail.xlsx` in the repository root before running the pipeline.

## Architecture

See [docs/architecture/overview.md](docs/architecture/overview.md) for the full data
flow diagram, database design rationale, and testing strategy.

## Technology stack

Python 3.11+, pandas, PostgreSQL, SQLAlchemy, psycopg, Pandera, pytest, Docker /
Docker Compose, Power BI Desktop, Streamlit (optional demo), ruff, GitHub Actions.

## KPI definitions

Every metric's exact formula and denominator is documented up front in
[docs/kpi_definitions.md](docs/kpi_definitions.md), including how cancellations and
returns are treated.

## Case study

A concise, portfolio-facing walkthrough (business problem, architecture, findings,
limitations) is in [docs/portfolio_case_study.md](docs/portfolio_case_study.md). Full
technical findings with every number traced to a query: `docs/business_insights.md`.

## Installation and setup

```bash
# 1. Clone and enter the repo
git clone <this-repo>
cd portfolio_

# 2. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev,dashboard]"

# 3. Configure environment variables
cp .env.example .env              # edit values if needed

# 4. Place the dataset
#    Download "Online Retail.xlsx" from the UCI link above and put it in the repo root.

# 5. Start PostgreSQL (requires Docker Desktop running)
docker compose up -d
```

On Windows without `make`, run the underlying commands directly — they're listed in
the `Makefile` and below.

## Running the pipeline

### Ingestion and profiling (Phase 2)

```bash
ingest-data              # or: python -m ecommerce_analytics.cli
ingest-data --force      # overwrite an existing raw copy whose checksum has drifted
```

What this does:

1. Validates the source `Online Retail.xlsx` has all required columns (fails fast on a
   missing/corrupt file or a missing column).
2. Copies it, byte-for-byte, into `data/raw/` and records a SHA-256 checksum sidecar
   file (`data/raw/Online Retail.xlsx.sha256`). On every subsequent run, the checksum
   is recomputed and compared — if it matches, no copy is made (the file is simply
   re-verified in place); if the raw copy has drifted from the source, the run is
   refused unless you pass `--force`, to stop an ingested raw file being silently
   overwritten.
3. Runs structural schema validation (column presence, dtypes, nullability) via
   Pandera — a **fatal** error here means the file isn't the dataset we expect.
4. Computes a full data profile and writes it to `reports/data_profile.json` (machine-
   readable) and `reports/data_profile.md` (human-readable), and logs a set of
   **non-fatal** data-quality warnings (see below) — a full execution log is written
   to `reports/ingestion.log`.

### Data quality findings from the real dataset (Phase 2 output, reproducible via the
command above — see `reports/data_profile.md` for the full report)

| Finding | Count | % of rows |
|---|---|---|
| Missing `CustomerID` | 135,080 | 24.93% |
| Missing `Description` | 1,454 | 0.27% |
| Fully duplicated rows | 5,268 | 0.97% |
| Negative `Quantity` | 10,624 | 1.96% |
| Non-positive `UnitPrice` (2 negative + 2,515 zero) | 2,517 | 0.46% |
| Cancellations (`InvoiceNo` starts with `C`) | 9,288 | 1.71% |
| Potential returns (negative quantity, not a cancellation-prefixed invoice) | 1,336 | 0.25% |

None of these rows are removed or modified in Phase 2 — they are classified in
Phase 3 (below), not silently dropped.

### Cleaning and transaction classification (Phase 3)

```bash
ingest-data clean         # or: python -m ecommerce_analytics.cli clean
ingest-data clean --force # same, overwriting a drifted raw copy first
```

What this does (re-uses the already checksum-verified raw file — parses the Excel file
exactly once per run):

1. Re-validates the raw data's structural schema.
2. Normalises dtypes (`CustomerID` -> nullable `Int64`, text columns stripped) and adds
   a deterministic `source_row_id` (0-based raw-file row position — a **technical**
   identifier, not a business transaction ID).
3. Classifies every row's `transaction_status` — `valid_sale`, `cancellation`,
   `potential_return`, or `non_standard` — by a documented precedence rule, and adds
   independent boolean flags (`flag_missing_customer_id`, `flag_duplicate_candidate`,
   etc.) that can coexist with any status. **No row is ever added, removed, or
   reclassified into a single catch-all bucket that loses information.**
4. Computes `line_revenue` per row using Python `Decimal` (not raw float64) to avoid
   rounding artefacts, and reconciles gross/net revenue totals in the report.
5. Runs fatal regression-guard validation (row count preserved, every row classified,
   `line_revenue` consistent with `quantity * unit_price`) — a failure here means a bug
   in the cleaning code itself, not a data-quality finding.
6. Saves the result to `data/processed/online_retail_cleaned.parquet` and writes
   `reports/cleaning_summary.json` / `.md`.

**Real classification results** (reproducible via the command above — full detail in
`reports/cleaning_summary.md` and the precedence rule in
[docs/kpi_definitions.md](docs/kpi_definitions.md)):

| `transaction_status` | Count | % of rows |
|---|---|---|
| `valid_sale` | 530,103 | 97.82% |
| `cancellation` | 9,288 | 1.71% |
| `potential_return` | 1,336 | 0.25% |
| `non_standard` | 1,182 | 0.22% |

Notable, verified findings (not assumed):
- **0** cancellation-prefixed invoices have non-negative quantity — the documented
  convention holds with no exceptions in this dataset.
- **All 1,336** `potential_return` rows have `UnitPrice == 0` and no `CustomerID` —
  they carry **£0.00** combined value, so they are excluded from net revenue (there is
  no refund amount to net off), not because negative quantity is assumed invalid.
- **3** rows have a non-standard `InvoiceNo` format entirely (`A563185`-style "Adjust
  bad debt" manual entries) — one has a *positive* price/quantity and would otherwise
  look like an ordinary sale; only the invoice-format check catches it.
- **10,147** rows (4,879 groups, largest group 20 rows) are exact-duplicate
  candidates — flagged, never auto-dropped.
- **Net revenue: £9,758,809.99** (gross sales £10,655,622.48 + cancellation value
  -£896,812.49).

### PostgreSQL warehouse loading (Phase 4)

```bash
docker compose up -d       # start PostgreSQL 16 (requires Docker Desktop running)
ingest-data load-warehouse # or: python -m ecommerce_analytics.cli load-warehouse
```

What this does (reads the already-cleaned Parquet file — does not re-run
ingestion/cleaning; connects to PostgreSQL on the port configured in `.env`, default
`5433`):

1. Idempotently applies the schema (`sql/schema/*.sql` — safe to re-run every time,
   never drops or alters existing objects).
2. Bulk-loads the cleaned dataset into a `staging` landing table via `COPY`.
3. Upserts dimension tables (`dim_product`, `dim_customer`, `dim_country`, `dim_date`)
   and then `fact_sales`, all inside **one transaction** — a failure anywhere rolls
   back everything.
4. Reconciles the warehouse against the source dataframe (row counts, transaction
   classification counts, missing-customer count, duplicate-candidate count, gross/
   cancellation/return/net revenue, monetary precision) and writes
   `reports/warehouse_load_report.{json,md}`.

Full schema design, ER diagram, and the idempotency/rollback strategy:
[docs/architecture/overview.md](docs/architecture/overview.md). Column-level detail:
[docs/data_dictionary.md](docs/data_dictionary.md).

**Real load results** (reproducible via the command above):

| Check | Result |
|---|---|
| `fact_sales` row count | **541,909** (matches the cleaned dataset exactly) |
| Transaction status counts | `valid_sale` 530,103 / `cancellation` 9,288 / `potential_return` 1,336 / `non_standard` 1,182 |
| Missing-customer rows (nullable FK, not invented) | 135,080 |
| Duplicate-candidate rows preserved | 10,147 |
| Gross sales revenue | £10,655,622.48 |
| Cancellation value | -£896,812.49 |
| **Net revenue** | **£9,758,809.99** |
| **All reconciliation checks** | **PASS** (12/12) |

**Idempotency verified**: the loader was run twice against the real dataset;
`fact_sales` had exactly 541,909 rows after both runs, with no duplicate-key errors.
**Rollback verified**: a deliberately broken load (null `transaction_status`) was
rejected and the transaction rolled back with `fact_sales` left unchanged.

**Example SQL queries** (against the analytical views in `sql/schema/006_views.sql`):

```sql
-- Monthly net revenue
SELECT year, month, net_revenue, order_count FROM warehouse.v_monthly_revenue;

-- Top 10 customers by revenue
SELECT customer_id, order_count, total_net_revenue
FROM warehouse.v_customer_summary
ORDER BY total_net_revenue DESC LIMIT 10;

-- Data-quality monitoring, live from the warehouse
SELECT * FROM warehouse.v_data_quality_monitor;
```

### Advanced SQL analysis and business intelligence (Phase 5)

No new command — this phase adds SQL, not a pipeline step. The database must already
be loaded (`ingest-data load-warehouse` above); the 10 new views are applied
automatically as part of that command (it re-applies the whole `sql/schema/`
directory every run). To run an illustrative analysis script directly, use `psql` if
you have it installed, or the project's own `psycopg` dependency:

```bash
# With psql:
psql -h localhost -p 5433 -U analytics_user -d ecommerce_analytics -f sql/analysis/010_sales_performance.sql

# Without psql (uses the same connection config as the rest of the project):
python -c "
from ecommerce_analytics.warehouse import build_engine
import sqlalchemy as sa
engine = build_engine()
sql = open('sql/analysis/010_sales_performance.sql').read()
with engine.connect() as conn:
    for stmt in [s for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]:
        for row in conn.execute(sa.text(stmt)):
            print(row)
"
```

10 new views (`sql/schema/007_phase5_views.sql`) covering monthly revenue growth
(with a genuinely-derived partial-month flag), revenue by country, product
rankings/trends/cancellation activity, RFM customer segmentation, cohort retention,
and duplicate-sensitivity analysis — plus 33 illustrative standalone queries in
`sql/analysis/*.sql`, organised by business area (sales, product, customer,
transaction quality, cohorts).

**Full real findings, with every number traced to its query**:
[docs/business_insights.md](docs/business_insights.md). Highlights:

| Finding | Value |
|---|---|
| Net revenue | £9,758,809.99 (19,959 orders, AOV £488.94) |
| Repeat customer rate | 65.58% (2,845 of 4,338 customers with a qualifying purchase) |
| Revenue concentration | Top 10% of customers = 59.80% of customer-attributable revenue |
| Mean vs. median customer spend | £1,915.74 vs. £655.34 (heavily right-skewed) |
| December 2011 | **Partial month** (9 of 31 days) — its -70.33% MoM figure is a truncation artefact, not a real trend |

A genuine performance issue was found and fixed by measurement: an early version of
`v_duplicate_sensitivity_delta` took 3.4s (it re-computed an expensive deduplication
window function 4 times); rewritten as a single-pass query, it takes 0.89s with
identical output — see `docs/architecture/overview.md` for the `EXPLAIN ANALYZE`
evidence.

### Power BI dashboard data export (Phase 6)

```bash
ingest-data export-powerbi   # or: python -m ecommerce_analytics.cli export-powerbi
```

Exports a deliberately minimal 9-table import model (the star schema plus 4 Phase 5
views whose logic is too complex to sanely re-derive in DAX) to
`dashboards/powerbi/data/*.csv`, then re-counts every source live in PostgreSQL to
verify each export matches exactly.

**No `.pbix`/`.pbip` file exists in this repository.** Power BI Desktop is installed
on the build machine, but it's a GUI-only application with no command-line interface,
and this environment has no screenshot/GUI-automation capability to drive it or
verify what it renders. Rather than hand-author a binary/project file with no way to
confirm it actually opens correctly, `dashboards/powerbi/` contains everything needed
to build it by hand quickly and correctly: the full data model (`DATA_MODEL.md`,
including which tables are deliberately left unrelated to prevent double-counting),
every DAX measure with its SQL-verified expected value (`DAX_MEASURES.md`), a
visual-by-visual spec for all 4 pages (`PAGE_SPECIFICATIONS.md`), and a user guide
(`DASHBOARD_USER_GUIDE.md`) — plus the real, row-count-verified CSV data itself.

## Running the tests

```bash
pytest        # or: make test
ruff check src tests   # or: make lint
```

Database integration tests (`tests/test_warehouse_integration.py`,
`tests/test_analysis.py`, `tests/test_powerbi_export.py`) run against a dedicated
`<database>_test` database (auto-created, never the real dev database) and are
**skipped automatically** if PostgreSQL isn't reachable — `pytest` still passes either
way. CI runs them for real, against a PostgreSQL 16 service container. 73 tests total
as of Phase 6.

## Project limitations

- Single historical snapshot, not a live data source.
- No product cost, margin, or shipping data — only revenue KPIs are possible.
- No customer demographics beyond country; no reliable UK sub-national geography.
- 24.93% of rows have no `CustomerID` — excluded from customer-level KPIs, included
  in product/revenue-level KPIs (see `docs/data_dictionary.md`).
- Passing schema and cleaning validation confirms internal consistency (row counts,
  classification completeness, revenue arithmetic) — it does not confirm every field
  was recorded correctly at the source. `non_standard`, `potential_return`, and
  duplicate-candidate rows (about 2.4% of rows combined) are reported separately
  rather than folded into "clean" data; see `docs/data_dictionary.md`.

## Future improvements

- Airflow/orchestrated scheduling, if extended beyond a portfolio demo.
- Cloud deployment (currently intentionally local-only: Docker Compose + Power
  BI/Streamlit).

## Licence

MIT for the code in this repository. The dataset itself is subject to the UCI ML
Repository's own terms — see the link above.
