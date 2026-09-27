import dataclasses

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

from ecommerce_analytics.config import load_database_config
from ecommerce_analytics.schema import SHEET_NAME

# A small, hand-crafted dataset with deliberately known statistics:
# - 8 rows, but row index 7 is an exact duplicate of row index 0 -> 1 duplicate row
# - 7 distinct InvoiceNo values (duplicate row reuses InvoiceNo 536001)
# - 5 distinct StockCode values, 3 distinct non-null CustomerID values, 4 countries
# - CustomerID missing on 2 rows, Description missing on 1 row
# - 1 cancellation (InvoiceNo starts with 'C', negative quantity)
# - 1 "potential return": negative quantity but NOT a cancellation-prefixed invoice
# - 1 row with UnitPrice == 0
_RECORDS = [
    # InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country
    ("536001", "10001", "WIDGET A", 6, "2011-01-01", 2.5, 1001.0, "United Kingdom"),
    ("536002", "10002", "WIDGET B", 3, "2011-01-02", 5.0, 1002.0, "France"),
    ("536003", "10001", "WIDGET A", 2, "2011-01-03", 2.5, 1001.0, "United Kingdom"),
    ("C536004", "10002", "WIDGET B", -1, "2011-01-04", 5.0, 1002.0, "France"),
    ("536005", "10003", None, 1, "2011-01-05", 0.0, None, "United Kingdom"),
    ("536006", "10004", "WIDGET D", -2, "2011-01-06", 3.0, 1003.0, "Germany"),
    ("536007", "10005", "WIDGET E", 4, "2011-01-07", 1.5, None, "Spain"),
    ("536001", "10001", "WIDGET A", 6, "2011-01-01", 2.5, 1001.0, "United Kingdom"),  # dup of row 0
]

_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]


@pytest.fixture
def sample_df() -> pd.DataFrame:
    df = pd.DataFrame(_RECORDS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return df


@pytest.fixture
def write_sample_xlsx(sample_df, tmp_path):
    """Returns a function that writes the sample dataframe (or a custom one) to an
    .xlsx file at the given path, using the correct sheet name."""

    def _write(path, df: pd.DataFrame | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        (df if df is not None else sample_df).to_excel(path, sheet_name=SHEET_NAME, index=False)
        return path

    return _write


# --- PostgreSQL integration test fixtures -----------------------------------------
#
# Integration tests run against a dedicated `<database>_test` database on the same
# Postgres server used by the rest of the project (created on demand), never the
# real development database — so tests can freely truncate tables without touching
# real loaded data. If Postgres isn't reachable at all (e.g. Docker Desktop isn't
# running, or in a CI job with no postgres service), every test using `db_engine` is
# skipped rather than failed, keeping the credential-free CI workflow functional.


@pytest.fixture(scope="session")
def db_engine():
    base_config = load_database_config()
    test_db_name = f"{base_config.name}_test"

    try:
        admin_engine = sa.create_engine(base_config.sqlalchemy_url, future=True)
        with admin_engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable - skipping warehouse integration tests")

    # CREATE DATABASE cannot run inside a transaction block, so this connection is
    # opened in AUTOCOMMIT mode specifically for the bootstrap check.
    autocommit_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    with autocommit_engine.connect() as conn:
        exists = conn.execute(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_db_name}
        ).first()
        if not exists:
            conn.execute(sa.text(f'CREATE DATABASE "{test_db_name}"'))
    admin_engine.dispose()

    test_config = dataclasses.replace(base_config, name=test_db_name)
    engine = sa.create_engine(test_config.sqlalchemy_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_warehouse(db_engine):
    """Idempotently (re-)applies the schema, then truncates every warehouse/staging
    table so each test starts from an empty, known state."""
    from ecommerce_analytics.warehouse import SCHEMA_DIR

    with db_engine.begin() as conn:
        for script in sorted(SCHEMA_DIR.glob("*.sql")):
            conn.execute(sa.text(script.read_text(encoding="utf-8")))
        conn.execute(
            sa.text(
                "TRUNCATE TABLE warehouse.fact_sales, warehouse.dim_product, "
                "warehouse.dim_customer, warehouse.dim_country, warehouse.dim_date, "
                "staging.stg_cleaned_sales"
            )
        )
    return db_engine
