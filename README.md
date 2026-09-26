# UK E-commerce Sales & Customer Intelligence Platform

An end-to-end analytics pipeline — ingestion, validated cleaning, a PostgreSQL star
schema, SQL business analysis, and dashboards — built on the UCI **Online Retail**
dataset, a historical (non-live) export of transactions from a UK-based online gift
retailer covering 2010-12-01 to 2011-12-09.

> **Status:** Phase 1 (planning & repository scaffold) complete. See
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

> Ingestion, cleaning, and database-loading commands will be documented here as each
> phase is implemented (Phase 2 onward). Not yet available.

## Running the tests

```bash
pytest        # or: make test
ruff check src tests   # or: make lint
```

## Project limitations

- Single historical snapshot, not a live data source.
- No product cost, margin, or shipping data — only revenue KPIs are possible.
- No customer demographics beyond country; no reliable UK sub-national geography.
- 24.9% of rows have no `CustomerID` — excluded from customer-level KPIs, included
  in product/revenue-level KPIs (see `docs/data_dictionary.md`).

## Future improvements

- Airflow/orchestrated scheduling, if extended beyond a portfolio demo.
- Cloud deployment (currently intentionally local-only: Docker Compose + Power
  BI/Streamlit).

## Licence

MIT for the code in this repository. The dataset itself is subject to the UCI ML
Repository's own terms — see the link above.
