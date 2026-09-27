"""Cached loading + lightweight schema validation for the public CSV extracts.

No PostgreSQL connection is used or required here — this is exactly the "must not
require a continuously running database" requirement for the public deployment. Local
development that needs to *refresh* these extracts uses `ingest-data export-public`
(which does talk to Postgres) as a separate, explicit step — never triggered by the
Streamlit app itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_lib.config import get_data_dir

logger = logging.getLogger(__name__)

# Column lists used for a lightweight presence check on load — not a full schema
# validator (that lives server-side in ecommerce_analytics.public_export), just a
# guard against a stale or partially-regenerated CSV silently producing wrong numbers.
EXPECTED_SCHEMAS: dict[str, list[str]] = {
    "product_performance": [
        "product_key", "stock_code", "description", "units_sold", "revenue",
        "order_count", "revenue_rank", "quantity_rank", "pct_of_total_revenue",
        "is_non_merchandise",
    ],
    "product_monthly_trend": [
        "stock_code", "description", "year", "month", "units_sold", "revenue",
    ],
    "product_cancellation_activity": [
        "stock_code", "description", "cancellation_count", "cancellation_value",
        "valid_sale_count", "cancellation_rate_pct",
    ],
    "product_country_performance": [
        "country_name", "stock_code", "description", "revenue", "rank_within_country",
    ],
    "country_performance": [
        "country_key", "country_name", "order_count", "gross_sales_revenue",
        "cancellation_value", "net_revenue", "revenue_rank",
    ],
    "monthly_revenue": [
        "year", "month", "month_start", "is_partial_month", "gross_sales_revenue",
        "cancellation_value", "net_revenue", "order_count", "average_order_value",
        "previous_month_net_revenue", "month_over_month_growth_pct",
        "cumulative_net_revenue",
    ],
    "cohort_retention": [
        "cohort_month", "activity_month", "month_index", "cohort_size",
        "returning_customers", "retention_pct", "dataset_last_month",
    ],
    "duplicate_sensitivity": [
        "dataset_version", "revenue", "order_count", "units_sold", "average_order_value",
    ],
    "transaction_quality_summary": [
        "transaction_status", "row_count", "missing_customer_id_count",
        "missing_description_count", "non_positive_price_count", "zero_quantity_count",
        "duplicate_candidate_count", "non_standard_invoice_format_count",
        "non_standard_stock_code_count",
    ],
    "anomalous_transactions": [
        "invoice_no", "quantity", "unit_price", "line_revenue", "transaction_status",
    ],
    "customer_segment_summary": [
        "rfm_segment_heuristic", "customer_count", "avg_recency_days",
        "avg_frequency", "avg_monetary",
    ],
    "customer_spend_deciles": [
        "decile", "customer_count", "decile_revenue", "pct_of_total_revenue",
    ],
    "customer_headline_metrics": [
        "identified_customers", "customers_with_qualifying_purchase",
        "customers_with_orders", "repeat_customers", "repeat_customer_rate_pct",
        "mean_customer_spend", "median_customer_spend", "top_decile_revenue",
        "top_decile_revenue_pct",
    ],
    "dataset_metadata": [
        "total_source_records", "date_range_start", "date_range_end",
        "valid_sale_count", "cancellation_count", "potential_return_count",
        "non_standard_count", "missing_customer_id_count",
        "duplicate_candidate_count", "anomalous_invoice_format_count",
    ],
    "dim_product": ["product_key", "stock_code", "description"],
}

# Columns that must be parsed as dates for downstream filtering/charting to work.
_DATE_COLUMNS: dict[str, list[str]] = {
    "monthly_revenue": ["month_start"],
    "cohort_retention": ["cohort_month", "activity_month", "dataset_last_month"],
    "dataset_metadata": ["date_range_start", "date_range_end"],
}


class DataLoadError(Exception):
    """Raised when a required public dataset is missing or fails the schema check."""


def validate_schema(name: str, df: pd.DataFrame) -> None:
    expected = EXPECTED_SCHEMAS.get(name)
    if expected is None:
        return
    missing = set(expected) - set(df.columns)
    if missing:
        raise DataLoadError(
            f"'{name}.csv' is missing expected column(s): {sorted(missing)}. "
            f"Regenerate with `ingest-data export-public`."
        )


def read_table(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Read and validate one table. Pure function (no Streamlit caching) so it's
    directly unit-testable; `load_table` below wraps this with `st.cache_data`."""
    resolved_dir = data_dir if data_dir is not None else get_data_dir()
    path = resolved_dir / f"{name}.csv"
    if not path.exists():
        raise DataLoadError(
            f"'{name}.csv' not found at {path}. Run `ingest-data export-public` "
            f"(requires a local PostgreSQL connection) to generate the public dataset."
        )
    df = pd.read_csv(path, parse_dates=_DATE_COLUMNS.get(name))
    validate_schema(name, df)
    return df


@st.cache_data(show_spinner=False)
def load_table(name: str) -> pd.DataFrame:
    return read_table(name)


@st.cache_data(show_spinner=False)
def load_all_tables() -> dict[str, pd.DataFrame]:
    tables = {}
    for name in EXPECTED_SCHEMAS:
        try:
            tables[name] = load_table(name)
        except DataLoadError as exc:
            logger.error("Failed to load '%s': %s", name, exc)
            raise
    return tables
