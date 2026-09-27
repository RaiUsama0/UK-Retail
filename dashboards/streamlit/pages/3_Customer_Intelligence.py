"""Page 3 — Customer Intelligence.

Deliberately shows only aggregated/segment-level customer data — no per-customer rows
exist anywhere in the public dataset (see dashboards/streamlit/data/public/README.md).
This means some visuals that would exist on the internal Power BI RFM page (e.g. a
per-customer Recency/Frequency scatter plot) are not reproduced here by design, not by
oversight — showing one would expose an identifiable individual purchasing history.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit_lib.charts import cohort_retention_heatmap, rfm_segment_bar  # noqa: E402
from streamlit_lib.config import PAGE_ICON  # noqa: E402
from streamlit_lib.data_loader import DataLoadError, load_table  # noqa: E402
from streamlit_lib.metrics import customer_headline_row  # noqa: E402
from streamlit_lib.ui import (  # noqa: E402
    format_count,
    format_currency,
    format_percent,
    render_footer,
    render_kpi_row,
)

st.set_page_config(page_title="Customer Intelligence", page_icon=PAGE_ICON, layout="wide")
st.title("👥 Customer Intelligence")

try:
    headline = customer_headline_row(load_table("customer_headline_metrics"))
    segment_df = load_table("customer_segment_summary")
    decile_df = load_table("customer_spend_deciles")
    cohort_df = load_table("cohort_retention")
except DataLoadError as exc:
    st.error(f"⚠️ Could not load required data: {exc}")
    st.stop()

st.caption(
    "All figures on this page are full-dataset, whole-period summaries — no date or "
    "country filter applies here, since the public dataset has no per-customer rows "
    "to recalculate from (a deliberate privacy design choice, not a missing feature)."
)

identified_count = int(headline["identified_customers"])
qualifying_count = int(headline["customers_with_qualifying_purchase"])
non_qualifying_count = identified_count - qualifying_count

render_kpi_row(
    [
        (
            "Identified customers",
            format_count(identified_count),
            "Distinct CustomerID values in the source data",
        ),
        (
            "With a qualifying purchase",
            format_count(qualifying_count),
            (
                f"{non_qualifying_count} identified customers have no valid_sale "
                "purchase (e.g. a cancellation with no matching sale) and are "
                "excluded from RFM/spend metrics below"
            ),
        ),
        (
            "Repeat customer rate",
            format_percent(float(headline["repeat_customer_rate_pct"])),
            ">= 2 distinct orders, among customers with a qualifying purchase",
        ),
    ]
)
render_kpi_row(
    [
        ("Mean customer spend", format_currency(float(headline["mean_customer_spend"])), None),
        (
            "Median customer spend",
            format_currency(float(headline["median_customer_spend"])),
            "Shown alongside the mean deliberately — spend is heavily right-skewed",
        ),
        (
            "Top 10% revenue share",
            format_percent(float(headline["top_decile_revenue_pct"])),
            "Share of customer-attributable revenue held by the top-spending 10%",
        ),
    ]
)

st.markdown("#### Customer spend distribution (by decile)")
st.caption(
    "Decile 1 = highest-spending 10% of customers. Shown as decile summaries, not "
    "individual customer values, to avoid exposing identifiable spending histories."
)
st.bar_chart(decile_df.set_index("decile")["pct_of_total_revenue"])

st.markdown("#### RFM segmentation")
st.info(
    "ℹ️ **RFM segments here are a scoring heuristic** (quartile thresholds on "
    "Recency/Frequency/Monetary) — not a scientifically validated behavioural "
    "model. \"Customer value\" below means revenue actually **observed** within "
    "this dataset's window, not a predicted future lifetime value.",
    icon="ℹ️",
)
col1, col2 = st.columns([2, 1])
with col1:
    st.plotly_chart(rfm_segment_bar(segment_df), use_container_width=True)
with col2:
    segment_columns = [
        "rfm_segment_heuristic", "customer_count", "avg_recency_days", "avg_frequency",
    ]
    st.dataframe(
        segment_df[segment_columns],
        use_container_width=True,
        hide_index=True,
    )
st.caption(
    "Purchase frequency shown here is the segment-average only — the public "
    "dataset doesn't publish a per-customer order-count distribution, to avoid "
    "exposing individual purchasing histories."
)

st.markdown("#### Customer cohort retention")
st.warning(
    "⚠️ **Observation-window limit**: cohorts formed near the end of the dataset "
    "(e.g. November/December 2011) have had little or no chance to show retention "
    "in later months, simply because those months aren't in the data. A blank or "
    "low cell for a recent cohort is an unobserved period, not confirmed churn.",
    icon="⚠️",
)
st.plotly_chart(cohort_retention_heatmap(cohort_df), use_container_width=True)

render_footer()
