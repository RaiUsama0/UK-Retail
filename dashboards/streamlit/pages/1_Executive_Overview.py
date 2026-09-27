"""Page 1 — Executive Overview."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit_lib.charts import monthly_revenue_trend, revenue_by_country_bar  # noqa: E402
from streamlit_lib.config import PAGE_ICON  # noqa: E402
from streamlit_lib.data_loader import DataLoadError, load_table  # noqa: E402
from streamlit_lib.metrics import (  # noqa: E402
    compute_headline_kpis,
    customer_headline_row,
    dataset_metadata_row,
    filter_monthly_revenue_by_date,
)
from streamlit_lib.ui import (  # noqa: E402
    format_count,
    format_currency,
    render_empty_state,
    render_footer,
    render_kpi_row,
    render_partial_month_warning,
    render_reporting_period_banner,
)

st.set_page_config(page_title="Executive Overview", page_icon=PAGE_ICON, layout="wide")
st.title("📊 Executive Overview")

try:
    monthly_df = load_table("monthly_revenue")
    country_df = load_table("country_performance")
    customer_headline = customer_headline_row(load_table("customer_headline_metrics"))
    metadata = dataset_metadata_row(load_table("dataset_metadata"))
except DataLoadError as exc:
    st.error(f"⚠️ Could not load required data: {exc}")
    st.stop()

render_reporting_period_banner(
    str(metadata["date_range_start"])[:10], str(metadata["date_range_end"])[:10]
)

# --- Date filter -----------------------------------------------------------------
min_month = monthly_df["month_start"].min()
max_month = monthly_df["month_start"].max()

st.markdown("#### Filters")
date_range = st.date_input(
    "Reporting period (filters the KPI cards and trend chart below)",
    value=(min_month, max_month),
    min_value=min_month,
    max_value=max_month,
)
if len(date_range) != 2:
    st.stop()  # user is mid-selection (only one endpoint picked so far)
start_date, end_date = date_range

filtered_monthly = filter_monthly_revenue_by_date(
    monthly_df, pd.Timestamp(start_date), pd.Timestamp(end_date)
)

if filtered_monthly.empty:
    render_empty_state("No months fall within the selected date range. Adjust the filter above.")
    st.stop()

if filtered_monthly["is_partial_month"].any():
    render_partial_month_warning("The selected period")

kpis = compute_headline_kpis(filtered_monthly)

st.markdown("#### Headline KPIs (recalculated for the selected period above)")
render_kpi_row(
    [
        (
            "Net revenue",
            format_currency(kpis.net_revenue),
            "Gross sales revenue + cancellation value",
        ),
        ("Gross sales revenue", format_currency(kpis.gross_sales_revenue), None),
        (
            "Total orders",
            format_count(kpis.order_count),
            "Distinct invoices, valid_sale rows only",
        ),
        (
            "Average order value",
            format_currency(kpis.average_order_value),
            "Net revenue ÷ total orders",
        ),
    ]
)
st.caption(
    f"Based on {kpis.months_included} month(s) in the selected period. "
    "Active Customers (below) is always a full-dataset figure — the public dataset "
    "has no per-month customer breakdown, so it cannot be recalculated for a "
    "sub-period without exposing transaction-level customer data (see "
    "dashboards/streamlit/data/public/README.md)."
)
render_kpi_row(
    [
        (
            "Active identified customers (full dataset)",
            format_count(int(customer_headline["customers_with_qualifying_purchase"])),
            "Customers with >= 1 qualifying (valid_sale) purchase, whole dataset",
        ),
    ]
)

st.markdown("#### Monthly revenue trend")
st.caption(
    "Hollow markers indicate a partial month. Line reflects only the months in your "
    "selected filter above."
)
st.plotly_chart(monthly_revenue_trend(filtered_monthly), use_container_width=True)

st.markdown("#### Revenue by country")
country_focus = st.multiselect(
    "Focus on specific countries (chart below only — does not affect the KPI cards "
    "above, since the public dataset has no per-country-per-month breakdown)",
    options=sorted(country_df["country_name"].unique()),
)
chart_countries = (
    country_df[country_df["country_name"].isin(country_focus)] if country_focus else country_df
)
if chart_countries.empty:
    render_empty_state("No countries match the current selection.")
else:
    st.plotly_chart(revenue_by_country_bar(chart_countries), use_container_width=True)
st.caption(
    "This chart always reflects the FULL reporting period (2010-12-01 to "
    "2011-12-09), regardless of the date filter above — country-level revenue is "
    "only available as a whole-dataset aggregate in the public dataset."
)

render_footer()
