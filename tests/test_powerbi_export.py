"""Tests for the Power BI export module. The DB-free tests check the export map's own
consistency; the integration tests run against a real PostgreSQL instance (see
conftest.py's `clean_warehouse` fixture) and are skipped automatically if unreachable.
"""

import csv

import pandas as pd
import pytest

from ecommerce_analytics.cleaning import clean_dataset
from ecommerce_analytics.powerbi_export import (
    EXPORT_SOURCES,
    export_all,
    export_table,
    verify_export,
)
from ecommerce_analytics.warehouse import load_warehouse

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
_ROWS = [
    ("800001", "30001", "GADGET A", 2, "2011-05-01 10:00", 4.5, 5001.0, "United Kingdom"),
    ("800002", "30002", "GADGET B", 1, "2011-05-02 11:00", 9.0, 5002.0, "United Kingdom"),
    ("C800003", "30001", "GADGET A", -1, "2011-05-03 09:00", 4.5, 5001.0, "United Kingdom"),
]


def test_export_sources_are_all_warehouse_qualified():
    for source in EXPORT_SOURCES.values():
        assert source.startswith(("warehouse.", "staging."))


def test_export_sources_names_are_unique():
    assert len(EXPORT_SOURCES) == len(set(EXPORT_SOURCES))


def test_export_sources_includes_the_full_star_schema():
    for table in ("fact_sales", "dim_date", "dim_product", "dim_customer", "dim_country"):
        assert table in EXPORT_SOURCES


@pytest.fixture
def cleaned_fixture() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return clean_dataset(df)


@pytest.fixture
def loaded_warehouse(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    return clean_warehouse


def test_export_table_writes_expected_row_and_column_count(loaded_warehouse, tmp_path):
    result = export_table("fact_sales", "warehouse.fact_sales", loaded_warehouse, tmp_path)

    assert result.row_count == 3
    assert result.path.exists()

    with result.path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        data_rows = list(reader)

    assert len(header) == result.column_count
    assert len(data_rows) == 3
    assert "source_row_id" in header
    assert "transaction_status" in header


def test_verify_export_passes_for_a_correct_export(loaded_warehouse, tmp_path):
    result = export_table("dim_customer", "warehouse.dim_customer", loaded_warehouse, tmp_path)
    assert verify_export(result, loaded_warehouse) is True


def test_verify_export_fails_if_csv_is_stale(loaded_warehouse, tmp_path):
    result = export_table("dim_customer", "warehouse.dim_customer", loaded_warehouse, tmp_path)

    # Simulate a stale export: the live table has since gained a row.
    import sqlalchemy as sa

    with loaded_warehouse.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO warehouse.dim_customer (customer_id) VALUES (999999)")
        )

    assert verify_export(result, loaded_warehouse) is False

    # cleanup so this test doesn't leak state into other tests sharing the fixture DB
    with loaded_warehouse.begin() as conn:
        conn.execute(sa.text("DELETE FROM warehouse.dim_customer WHERE customer_id = 999999"))


def test_export_all_exports_every_configured_source(loaded_warehouse, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    exported_names = {r.name for r in results}
    assert exported_names == set(EXPORT_SOURCES)
    for r in results:
        assert verify_export(r, loaded_warehouse)
