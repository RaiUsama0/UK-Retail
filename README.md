# UK E-commerce Sales & Customer Intelligence Platform

An end-to-end analytics pipeline — ingestion, validated cleaning, a PostgreSQL star
schema, SQL business analysis, and dashboards — built on the UCI **Online Retail**
dataset, a historical (non-live) export of transactions from a UK-based online gift
retailer covering 2010-12-01 to 2011-12-09.

> **Status:** Phase 3 (data cleaning, transaction classification & validation) complete. See
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

### Database loading and beyond

> Not yet available — Phase 4 onward.

## Running the tests

```bash
pytest        # or: make test
ruff check src tests   # or: make lint
```

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
