"""Page 2 — Product and Sales Performance."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit_lib.charts import (  # noqa: E402
    product_revenue_contribution,
    top_products_bar,
)
from streamlit_lib.config import PAGE_ICON  # noqa: E402
from streamlit_lib.data_loader import DataLoadError, load_table  # noqa: E402
from streamlit_lib.ui import render_empty_state, render_footer  # noqa: E402

st.set_page_config(page_title="Product Performance", page_icon=PAGE_ICON, layout="wide")
st.title("📦 Product and Sales Performance")

try:
    products_df = load_table("product_performance")
    trend_df = load_table("product_monthly_trend")
    country_products_df = load_table("product_country_performance")
    cancellation_df = load_table("product_cancellation_activity")
except DataLoadError as exc:
    st.error(f"⚠️ Could not load required data: {exc}")
    st.stop()

st.warning(
    "⚠️ **Two rankings on this page need context before you trust them at face "
    "value:** the highest-revenue \"product\" (`DOT`, DOTCOM POSTAGE) is a shipping "
    "charge, not a merchandise item — it's a genuine charge, so it's correctly "
    "included, but it isn't a sold product. The highest-quantity product "
    "(`23843`, PAPER CRAFT LITTLE BIRDIE) owes nearly all of its 80,995 units to a "
    "**single bulk order**, not broad demand.",
    icon="⚠️",
)

merch_filter = st.radio(
    "Show:",
    ["All products", "Merchandise only", "Non-merchandise charges only"],
    horizontal=True,
)
if merch_filter == "Merchandise only":
    view_df = products_df[~products_df["is_non_merchandise"]]
elif merch_filter == "Non-merchandise charges only":
    view_df = products_df[products_df["is_non_merchandise"]]
else:
    view_df = products_df

search = st.text_input("Search products by description or stock code")
if search:
    mask = view_df["description"].str.contains(search, case=False, na=False) | view_df[
        "stock_code"
    ].str.contains(search, case=False, na=False)
    view_df = view_df[mask]

if view_df.empty:
    render_empty_state("No products match the current filter/search.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Top 10 by revenue")
    st.plotly_chart(
        top_products_bar(view_df.nsmallest(10, "revenue_rank"), "revenue", "Revenue (£)"),
        use_container_width=True,
    )
with col2:
    st.markdown("#### Top 10 by quantity sold")
    st.plotly_chart(
        top_products_bar(view_df.nsmallest(10, "quantity_rank"), "units_sold", "Units sold"),
        use_container_width=True,
    )

st.markdown("#### Revenue contribution (top 10 vs. all other products)")
st.plotly_chart(product_revenue_contribution(view_df), use_container_width=True)

st.markdown("#### Monthly trend for a selected product")
product_options = view_df.sort_values("revenue_rank")["description"].tolist()
selected_product = st.selectbox("Choose a product", options=product_options)
if selected_product:
    product_trend = trend_df[trend_df["description"] == selected_product].sort_values(
        ["year", "month"]
    )
    if product_trend.empty:
        render_empty_state("No monthly data for this product.")
    else:
        product_trend = product_trend.assign(
            month_start=pd.to_datetime(
                product_trend["year"].astype(str) + "-" + product_trend["month"].astype(str) + "-01"
            )
        )
        st.line_chart(product_trend.set_index("month_start")[["revenue", "units_sold"]])

st.markdown("#### Country-level product performance (top 20 products per country)")
country_options = sorted(country_products_df["country_name"].unique())
default_index = (
    country_options.index("United Kingdom") if "United Kingdom" in country_options else 0
)
selected_country = st.selectbox("Country", options=country_options, index=default_index)
country_table = country_products_df[
    country_products_df["country_name"] == selected_country
].sort_values("rank_within_country")
st.dataframe(
    country_table[["rank_within_country", "stock_code", "description", "revenue"]],
    use_container_width=True,
    hide_index=True,
    column_config={"revenue": st.column_config.NumberColumn("Revenue", format="£%.2f")},
)
st.caption(
    "Limited to each country's top 20 products by revenue (see "
    "dashboards/streamlit/data/public/README.md for why the full cross-join isn't "
    "published)."
)

st.markdown("#### Cancellation activity")
st.caption(
    "Products with at least one cancellation, ranked by cancellation count. A "
    "cancellation is not the same as a confirmed refund of a specific amount — see "
    "the Transaction Quality page for the full definition."
)
cancellation_columns = [
    "stock_code",
    "description",
    "cancellation_count",
    "cancellation_value",
    "cancellation_rate_pct",
]
st.dataframe(
    cancellation_df.sort_values("cancellation_count", ascending=False).head(15)[
        cancellation_columns
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "cancellation_value": st.column_config.NumberColumn("Cancellation value", format="£%.2f"),
        "cancellation_rate_pct": st.column_config.NumberColumn(
            "Cancellation rate", format="%.2f%%"
        ),
    },
)

render_footer()
