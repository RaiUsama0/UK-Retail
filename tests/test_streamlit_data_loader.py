"""Tests for the public-CSV data loader: schema validation and missing-file handling."""

import pandas as pd
import pytest

from streamlit_lib.data_loader import DataLoadError, read_table, validate_schema


def test_validate_schema_passes_when_all_columns_present():
    df = pd.DataFrame(columns=["product_key", "stock_code", "description"])
    validate_schema("dim_product", df)  # should not raise


def test_validate_schema_raises_on_missing_column():
    df = pd.DataFrame(columns=["product_key", "stock_code"])  # missing "description"
    with pytest.raises(DataLoadError, match="description"):
        validate_schema("dim_product", df)


def test_validate_schema_is_a_no_op_for_unknown_table_name():
    df = pd.DataFrame({"anything": [1, 2]})
    validate_schema("not_a_real_table", df)  # should not raise


def test_read_table_raises_clear_error_when_file_missing(tmp_path):
    with pytest.raises(DataLoadError, match="export-public"):
        read_table("dim_product", data_dir=tmp_path)


def test_read_table_loads_and_validates_a_real_file(tmp_path):
    df = pd.DataFrame({"product_key": [1], "stock_code": ["A"], "description": ["Widget"]})
    df.to_csv(tmp_path / "dim_product.csv", index=False)

    loaded = read_table("dim_product", data_dir=tmp_path)
    assert list(loaded.columns) == ["product_key", "stock_code", "description"]
    assert len(loaded) == 1


def test_read_table_raises_on_a_corrupted_schema(tmp_path):
    df = pd.DataFrame({"product_key": [1], "stock_code": ["A"]})  # missing description
    df.to_csv(tmp_path / "dim_product.csv", index=False)

    with pytest.raises(DataLoadError, match="missing expected column"):
        read_table("dim_product", data_dir=tmp_path)


def test_read_table_parses_date_columns(tmp_path):
    df = pd.DataFrame(
        {
            "year": [2011],
            "month": [1],
            "month_start": ["2011-01-01"],
            "is_partial_month": [False],
            "gross_sales_revenue": [100.0],
            "cancellation_value": [0.0],
            "net_revenue": [100.0],
            "order_count": [1],
            "average_order_value": [100.0],
            "previous_month_net_revenue": [None],
            "month_over_month_growth_pct": [None],
            "cumulative_net_revenue": [100.0],
        }
    )
    df.to_csv(tmp_path / "monthly_revenue.csv", index=False)

    loaded = read_table("monthly_revenue", data_dir=tmp_path)
    assert pd.api.types.is_datetime64_any_dtype(loaded["month_start"])
