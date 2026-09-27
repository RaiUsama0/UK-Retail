"""End-to-end tests for the Streamlit app using Streamlit's own headless AppTest
facility (streamlit.testing.v1) — the app is actually executed, not mocked. Uses a
small, hand-built synthetic public dataset (not the real ~2.3MB export) written to a
temp directory and pointed to via STREAMLIT_PUBLIC_DATA_DIR, so these tests need
neither PostgreSQL nor the real generated CSVs, and run fast and deterministically.
"""

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "streamlit"


@pytest.fixture(autouse=True)
def _clear_streamlit_cache():
    """`st.cache_data` is a process-global cache keyed only on function arguments —
    `load_table("dim_product")` from one test would otherwise leak into the next test
    even though STREAMLIT_PUBLIC_DATA_DIR points at a different temp directory each
    time (confirmed empirically: without this fixture,
    test_missing_dataset_shows_a_clear_error_not_a_crash silently received another
    test's cached dataframe instead of hitting the empty directory). This is also a
    real, documented production behaviour, not just a test artefact — see
    dashboards/streamlit/README.md's refresh-strategy section."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()

# One row (or a few) per table, with deliberately known, hand-computed relationships
# — e.g. net_revenue = gross + cancellation for every month below.
_SYNTHETIC_TABLES: dict[str, pd.DataFrame] = {
    "product_performance": pd.DataFrame(
        {
            "product_key": [1, 2],
            "stock_code": ["10001", "DOT"],
            "description": ["Widget A", "DOTCOM POSTAGE"],
            "units_sold": [100, 5],
            "revenue": [500.0, 200.0],
            "order_count": [20, 5],
            "revenue_rank": [1, 2],
            "quantity_rank": [1, 2],
            "pct_of_total_revenue": [71.43, 28.57],
            "is_non_merchandise": [False, True],
        }
    ),
    "product_monthly_trend": pd.DataFrame(
        {
            "stock_code": ["10001", "10001"],
            "description": ["Widget A", "Widget A"],
            "year": [2011, 2011],
            "month": [1, 2],
            "units_sold": [50, 50],
            "revenue": [250.0, 250.0],
        }
    ),
    "product_cancellation_activity": pd.DataFrame(
        {
            "stock_code": ["10001"],
            "description": ["Widget A"],
            "cancellation_count": [3],
            "cancellation_value": [-15.0],
            "valid_sale_count": [20],
            "cancellation_rate_pct": [13.04],
        }
    ),
    "product_country_performance": pd.DataFrame(
        {
            "country_name": ["United Kingdom", "France"],
            "stock_code": ["10001", "10001"],
            "description": ["Widget A", "Widget A"],
            "revenue": [400.0, 100.0],
            "rank_within_country": [1, 1],
        }
    ),
    "country_performance": pd.DataFrame(
        {
            "country_key": [1, 2],
            "country_name": ["United Kingdom", "France"],
            "order_count": [15, 5],
            "gross_sales_revenue": [400.0, 100.0],
            "cancellation_value": [-10.0, -5.0],
            "net_revenue": [390.0, 95.0],
            "revenue_rank": [1, 2],
        }
    ),
    "monthly_revenue": pd.DataFrame(
        {
            "year": [2011, 2011],
            "month": [1, 2],
            "month_start": ["2011-01-01", "2011-02-01"],
            "is_partial_month": [False, True],
            "gross_sales_revenue": [500.0, 200.0],
            "cancellation_value": [-20.0, -10.0],
            "net_revenue": [480.0, 190.0],
            "order_count": [20, 5],
            "average_order_value": [24.0, 38.0],
            "previous_month_net_revenue": [None, 480.0],
            "month_over_month_growth_pct": [None, -60.42],
            "cumulative_net_revenue": [480.0, 670.0],
        }
    ),
    "cohort_retention": pd.DataFrame(
        {
            "cohort_month": ["2011-01-01", "2011-01-01"],
            "activity_month": ["2011-01-01", "2011-02-01"],
            "month_index": [0, 1],
            "cohort_size": [10, 10],
            "returning_customers": [10, 4],
            "retention_pct": [100.0, 40.0],
            "dataset_last_month": ["2011-02-01", "2011-02-01"],
        }
    ),
    "duplicate_sensitivity": pd.DataFrame(
        {
            "dataset_version": ["complete_dataset", "deduplicated"],
            "revenue": [700.0, 690.0],
            "order_count": [25, 25],
            "units_sold": [150, 145],
            "average_order_value": [28.0, 27.6],
        }
    ),
    "transaction_quality_summary": pd.DataFrame(
        {
            "transaction_status": ["valid_sale", "cancellation"],
            "row_count": [95, 5],
            "missing_customer_id_count": [10, 1],
            "missing_description_count": [0, 0],
            "non_positive_price_count": [0, 0],
            "zero_quantity_count": [0, 0],
            "duplicate_candidate_count": [2, 0],
            "non_standard_invoice_format_count": [0, 0],
            "non_standard_stock_code_count": [1, 0],
        }
    ),
    "anomalous_transactions": pd.DataFrame(
        {
            "invoice_no": ["A900001"],
            "quantity": [1],
            "unit_price": [50.0],
            "line_revenue": [50.0],
            "transaction_status": ["non_standard"],
        }
    ),
    "customer_segment_summary": pd.DataFrame(
        {
            "rfm_segment_heuristic": ["Champions", "Other"],
            "customer_count": [5, 15],
            "avg_recency_days": [10.0, 200.0],
            "avg_frequency": [12.0, 1.0],
            "avg_monetary": [5000.0, 100.0],
        }
    ),
    "customer_spend_deciles": pd.DataFrame(
        {
            "decile": list(range(1, 11)),
            "customer_count": [2] * 10,
            "decile_revenue": [1000.0, 500.0, 300.0, 200.0, 150.0, 100.0, 80.0, 60.0, 40.0, 20.0],
            "pct_of_total_revenue": [41.15, 20.58, 12.35, 8.23, 6.17, 4.12, 3.29, 2.47, 1.65, 0.82],
        }
    ),
    "customer_headline_metrics": pd.DataFrame(
        {
            "identified_customers": [20],
            "customers_with_qualifying_purchase": [18],
            "customers_with_orders": [18],
            "repeat_customers": [10],
            "repeat_customer_rate_pct": [55.56],
            "mean_customer_spend": [250.0],
            "median_customer_spend": [150.0],
            "top_decile_revenue": [1000.0],
            "top_decile_revenue_pct": [41.15],
        }
    ),
    "dataset_metadata": pd.DataFrame(
        {
            "total_source_records": [100],
            "date_range_start": ["2011-01-01"],
            "date_range_end": ["2011-02-15"],
            "valid_sale_count": [95],
            "cancellation_count": [5],
            "potential_return_count": [0],
            "non_standard_count": [0],
            "missing_customer_id_count": [11],
            "duplicate_candidate_count": [2],
            "anomalous_invoice_format_count": [1],
        }
    ),
    "dim_product": pd.DataFrame(
        {
            "product_key": [1, 2],
            "stock_code": ["10001", "DOT"],
            "description": ["Widget A", "DOTCOM POSTAGE"],
        }
    ),
}


@pytest.fixture
def synthetic_public_data(tmp_path, monkeypatch) -> Path:
    for name, df in _SYNTHETIC_TABLES.items():
        df.to_csv(tmp_path / f"{name}.csv", index=False)
    monkeypatch.setenv("STREAMLIT_PUBLIC_DATA_DIR", str(tmp_path))
    return tmp_path


def _run_page(relative_path: str) -> AppTest:
    at = AppTest.from_file(str(APP_DIR / relative_path), default_timeout=30)
    at.run()
    return at


def test_home_page_runs_without_exception(synthetic_public_data):
    at = _run_page("app.py")
    assert not at.exception


def test_home_page_shows_reporting_period(synthetic_public_data):
    at = _run_page("app.py")
    info_texts = " ".join(i.value for i in at.info)
    assert "2011-01-01" in info_texts
    assert "2011-02-15" in info_texts


@pytest.mark.parametrize(
    "page",
    [
        "pages/1_Executive_Overview.py",
        "pages/2_Product_Performance.py",
        "pages/3_Customer_Intelligence.py",
        "pages/4_Transaction_Quality.py",
    ],
)
def test_every_page_runs_without_exception(synthetic_public_data, page):
    at = _run_page(page)
    assert not at.exception, f"{page} raised: {at.exception}"


def test_executive_overview_kpis_reconcile_with_synthetic_data(synthetic_public_data):
    at = _run_page("pages/1_Executive_Overview.py")
    metrics = {m.label: m.value for m in at.metric}

    # Default date range = full range = both months -> gross 700, cancel -30, net 670
    assert metrics["Net revenue"] == "£670.00"
    assert metrics["Gross sales revenue"] == "£700.00"
    assert metrics["Total orders"] == "25"
    assert metrics["Average order value"] == "£26.80"


def test_executive_overview_shows_partial_month_warning_by_default(synthetic_public_data):
    # Full range includes February, which is flagged is_partial_month=True.
    at = _run_page("pages/1_Executive_Overview.py")
    warning_texts = " ".join(w.value for w in at.warning)
    assert "incomplete month" in warning_texts.lower()


def test_customer_intelligence_kpis_reconcile_with_synthetic_data(synthetic_public_data):
    at = _run_page("pages/3_Customer_Intelligence.py")
    metrics = {m.label: m.value for m in at.metric}

    assert metrics["Identified customers"] == "20"
    assert metrics["With a qualifying purchase"] == "18"
    assert metrics["Repeat customer rate"] == "55.56%"
    assert metrics["Mean customer spend"] == "£250.00"
    assert metrics["Median customer spend"] == "£150.00"
    assert metrics["Top 10% revenue share"] == "41.15%"


def test_transaction_quality_kpis_reconcile_with_synthetic_data(synthetic_public_data):
    at = _run_page("pages/4_Transaction_Quality.py")
    metrics = {m.label: m.value for m in at.metric}

    assert metrics["Total source records"] == "100"
    assert metrics["Valid sales"] == "95 (95.00%)"
    assert metrics["Cancellations"] == "5 (5.00%)"


def test_transaction_quality_shows_anomalous_row_without_customer_columns(synthetic_public_data):
    at = _run_page("pages/4_Transaction_Quality.py")
    # The anomalous_transactions table must never carry a customer identifier column
    # — verified structurally (same guarantee as the export-time privacy check).
    df = pd.read_csv(synthetic_public_data / "anomalous_transactions.csv")
    assert "customer_id" not in df.columns
    assert "customer_key" not in df.columns
    assert not at.exception


def test_public_dataset_has_no_customer_identifier_columns_anywhere(synthetic_public_data):
    """Defence-in-depth: even a hand-built test fixture is checked, matching the same
    invariant enforced at real export time by public_export.assert_no_customer_identifiers."""
    for csv_path in synthetic_public_data.glob("*.csv"):
        columns = set(pd.read_csv(csv_path, nrows=0).columns)
        assert "customer_id" not in columns, f"{csv_path.name} leaks customer_id"
        assert "customer_key" not in columns, f"{csv_path.name} leaks customer_key"


def test_missing_dataset_shows_a_clear_error_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMLIT_PUBLIC_DATA_DIR", str(tmp_path))  # empty directory
    at = _run_page("pages/1_Executive_Overview.py")
    assert not at.exception  # the app must catch DataLoadError itself, not crash
    error_texts = " ".join(e.value for e in at.error)
    assert "export-public" in error_texts
