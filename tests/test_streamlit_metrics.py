"""Unit tests for the Streamlit app's pure metric functions — no Streamlit runtime,
no database, no fixtures beyond small hand-built dataframes with known expected
results. Requires dashboards/streamlit on sys.path (configured via pyproject.toml's
pytest `pythonpath`).
"""

import pandas as pd

from streamlit_lib.metrics import (
    compute_headline_kpis,
    filter_by_column_values,
    filter_monthly_revenue_by_date,
    filter_product_country_performance,
    safe_divide,
    top_products_from_monthly_trend,
)


def test_safe_divide_normal_case():
    assert safe_divide(100, 4) == 25


def test_safe_divide_zero_denominator_returns_none():
    assert safe_divide(100, 0) is None


def test_safe_divide_none_denominator_returns_none():
    assert safe_divide(100, None) is None


def _sample_monthly_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month_start": pd.to_datetime(["2011-01-01", "2011-02-01", "2011-03-01"]),
            "is_partial_month": [False, False, True],
            "gross_sales_revenue": [1000.0, 2000.0, 500.0],
            "cancellation_value": [-100.0, -200.0, -50.0],
            "order_count": [10, 20, 5],
        }
    )


def test_filter_monthly_revenue_by_date_subsets_correctly():
    df = _sample_monthly_df()
    filtered = filter_monthly_revenue_by_date(
        df, pd.Timestamp("2011-01-01"), pd.Timestamp("2011-02-28")
    )
    assert len(filtered) == 2
    assert filtered["month_start"].max() == pd.Timestamp("2011-02-01")


def test_compute_headline_kpis_full_range():
    df = _sample_monthly_df()
    kpis = compute_headline_kpis(df)

    assert kpis.gross_sales_revenue == 3500.0
    assert kpis.cancellation_value == -350.0
    assert kpis.net_revenue == 3150.0
    assert kpis.order_count == 35
    assert kpis.average_order_value == 90.0
    assert kpis.months_included == 3
    assert kpis.has_partial_month is True


def test_compute_headline_kpis_excludes_partial_month_when_filtered():
    df = _sample_monthly_df()
    filtered = filter_monthly_revenue_by_date(
        df, pd.Timestamp("2011-01-01"), pd.Timestamp("2011-02-28")
    )
    kpis = compute_headline_kpis(filtered)

    assert kpis.net_revenue == 2700.0  # (1000-100) + (2000-200)
    assert kpis.has_partial_month is False


def test_compute_headline_kpis_zero_orders_gives_blank_aov():
    df = pd.DataFrame(
        {
            "gross_sales_revenue": [0.0],
            "cancellation_value": [0.0],
            "order_count": [0],
            "is_partial_month": [False],
        }
    )
    kpis = compute_headline_kpis(df)
    assert kpis.average_order_value is None


def test_top_products_from_monthly_trend_recomputes_for_selected_range():
    trend_df = pd.DataFrame(
        {
            "stock_code": ["A", "A", "B", "B"],
            "description": ["Widget A", "Widget A", "Widget B", "Widget B"],
            "year": [2011, 2011, 2011, 2011],
            "month": [1, 2, 1, 2],
            "units_sold": [10, 20, 100, 5],
            "revenue": [100.0, 200.0, 50.0, 10.0],
        }
    )
    # Restrict to January only: product B should outrank A within this window,
    # even though B trails A over the full two-month period (60 vs 300 revenue).
    result = top_products_from_monthly_trend(
        trend_df, pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-31")
    )
    assert result.iloc[0]["stock_code"] == "A"
    assert result.iloc[0]["revenue"] == 100.0
    assert len(result) == 2


def test_filter_product_country_performance_no_selection_returns_all():
    df = pd.DataFrame({"country_name": ["UK", "France"], "revenue": [100, 50]})
    assert len(filter_product_country_performance(df, None)) == 2
    assert len(filter_product_country_performance(df, [])) == 2


def test_filter_product_country_performance_filters_to_selection():
    df = pd.DataFrame({"country_name": ["UK", "France", "UK"], "revenue": [100, 50, 30]})
    result = filter_product_country_performance(df, ["France"])
    assert len(result) == 1
    assert result.iloc[0]["country_name"] == "France"


def test_filter_by_column_values_generic():
    df = pd.DataFrame({"segment": ["A", "B", "A"], "value": [1, 2, 3]})
    result = filter_by_column_values(df, "segment", ["A"])
    assert len(result) == 2
    assert (result["segment"] == "A").all()
