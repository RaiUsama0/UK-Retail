"""Tests for the public (Streamlit) export module. DB-free tests check the export
map's own privacy invariants; integration tests run against a real PostgreSQL
instance and are skipped automatically if unreachable.
"""

import pandas as pd
import pytest

from ecommerce_analytics.cleaning import clean_dataset
from ecommerce_analytics.public_export import (
    _DIMENSION_EXPORTS,
    _DIRECT_VIEW_EXPORTS,
    PublicExportError,
    assert_no_customer_identifiers,
    export_all,
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
    ("900001", "40001", "WIDGET X", 3, "2011-06-01 10:00", 6.0, 6001.0, "United Kingdom"),
    ("900002", "40002", "WIDGET Y", 2, "2011-06-15 11:00", 8.0, 6002.0, "France"),
    ("C900003", "40001", "WIDGET X", -1, "2011-06-20 09:00", 6.0, 6001.0, "United Kingdom"),
    ("900004", "POST", "POSTAGE", 1, "2011-07-01 09:00", 15.0, 6001.0, "United Kingdom"),
    # Anomalous invoice format (doesn't match ^C?\d{6}$), mirroring the real
    # "Adjust bad debt" rows found in Phase 3 — positive qty/price, no CustomerID.
    ("A900005", "B", "Adjust bad debt", 1, "2011-07-05 09:00", 50.0, None, "United Kingdom"),
]


def test_dimension_exports_have_no_customer_columns():
    for name, query in _DIMENSION_EXPORTS.items():
        assert "customer" not in query.lower(), f"{name} query references customer data"


@pytest.fixture
def cleaned_fixture() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return clean_dataset(df)


@pytest.fixture
def loaded_warehouse(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    return clean_warehouse


def test_export_all_produces_expected_tables(loaded_warehouse, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    names = {r.name for r in results}
    assert names == set(_DIRECT_VIEW_EXPORTS) | set(_DIMENSION_EXPORTS)
    for r in results:
        assert r.path.exists()
        assert r.row_count >= 0


def test_dataset_metadata_reconciles_with_fixture(loaded_warehouse, cleaned_fixture, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    metadata_path = next(r.path for r in results if r.name == "dataset_metadata")
    metadata = pd.read_csv(metadata_path).iloc[0]

    assert metadata["total_source_records"] == len(cleaned_fixture)
    assert metadata["anomalous_invoice_format_count"] == int(
        cleaned_fixture["flag_non_standard_invoice_format"].sum()
    )


def test_customer_headline_metrics_has_no_identifier_columns(loaded_warehouse, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    path = next(r.path for r in results if r.name == "customer_headline_metrics")
    columns = set(pd.read_csv(path).columns)
    assert "customer_id" not in columns
    assert "customer_key" not in columns


def test_anomalous_transactions_excludes_customer_columns(loaded_warehouse, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    path = next(r.path for r in results if r.name == "anomalous_transactions")
    df = pd.read_csv(path)
    assert "customer_id" not in df.columns
    assert "customer_key" not in df.columns
    assert "source_row_id" not in df.columns
    assert len(df) == 1  # the single anomalous-invoice-format row ("A900005")
    assert df.iloc[0]["invoice_no"] == "A900005"


def test_assert_no_customer_identifiers_passes_on_a_clean_export(loaded_warehouse, tmp_path):
    results = export_all(loaded_warehouse, tmp_path)
    assert_no_customer_identifiers(results)  # should not raise


def test_assert_no_customer_identifiers_catches_a_leaked_file(tmp_path):
    from ecommerce_analytics.public_export import PublicExportResult

    leaky_path = tmp_path / "leaky.csv"
    pd.DataFrame({"customer_id": [1, 2], "monetary": [10.0, 20.0]}).to_csv(
        leaky_path, index=False
    )
    fake_result = PublicExportResult(name="leaky", row_count=2, column_count=2, path=leaky_path)

    with pytest.raises(PublicExportError, match="customer_id"):
        assert_no_customer_identifiers([fake_result])
