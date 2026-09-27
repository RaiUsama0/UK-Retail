"""Page 4 — Transaction Quality and Data Reliability."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from streamlit_lib.charts import duplicate_sensitivity_bars, transaction_status_donut  # noqa: E402
from streamlit_lib.config import PAGE_ICON  # noqa: E402
from streamlit_lib.data_loader import DataLoadError, load_table  # noqa: E402
from streamlit_lib.metrics import dataset_metadata_row  # noqa: E402
from streamlit_lib.ui import (  # noqa: E402
    format_count,
    format_currency,
    format_percent,
    render_footer,
    render_kpi_row,
)

st.set_page_config(page_title="Transaction Quality", page_icon=PAGE_ICON, layout="wide")
st.title("🔍 Transaction Quality and Data Reliability")

try:
    metadata = dataset_metadata_row(load_table("dataset_metadata"))
    quality_df = load_table("transaction_quality_summary")
    sensitivity_df = load_table("duplicate_sensitivity")
    anomalous_df = load_table("anomalous_transactions")
except DataLoadError as exc:
    st.error(f"⚠️ Could not load required data: {exc}")
    st.stop()

st.caption(
    "This page always reports on the complete dataset (541,909 raw transaction "
    "lines) — no date/country filter applies, so that data-quality figures are "
    "never partially hidden by a filter selection."
)

total = int(metadata["total_source_records"])


def _count_and_share(count: int) -> str:
    return f"{format_count(count)} ({count / total:.2%})"


valid_sale_count = int(metadata["valid_sale_count"])
cancellation_count = int(metadata["cancellation_count"])
potential_return_count = int(metadata["potential_return_count"])
non_standard_count = int(metadata["non_standard_count"])

render_kpi_row(
    [
        ("Total source records", format_count(total), None),
        ("Valid sales", _count_and_share(valid_sale_count), None),
        ("Cancellations", _count_and_share(cancellation_count), None),
    ]
)
render_kpi_row(
    [
        (
            "Potential returns",
            _count_and_share(potential_return_count),
            "Negative quantity, NOT cancellation-prefixed — not a confirmed refund",
        ),
        (
            "Non-standard transactions",
            _count_and_share(non_standard_count),
            "Includes the 3 anomalous-invoice-format rows shown below",
        ),
        (
            "Missing customer identifier",
            format_percent(100 * int(metadata["missing_customer_id_count"]) / total),
            "Not necessarily invalid — many are legitimate guest-style sales",
        ),
    ]
)

st.info(
    "ℹ️ **Potential returns are not confirmed refunds.** In this dataset, every "
    "potential-return row has £0 unit price — so they carry no monetary weight in "
    "net revenue, and are reported here purely for transparency, not because a "
    "refund was actually issued.",
    icon="ℹ️",
)

st.markdown("#### Transaction status breakdown")
st.plotly_chart(transaction_status_donut(quality_df), use_container_width=True)

st.markdown("#### The 3 anomalous invoice-format records")
st.warning(
    "⚠️ These 3 rows don't match the dataset's normal invoice-number pattern at "
    "all (a set of \"Adjust bad debt\" manual accounting entries). None has a "
    "CustomerID attached, so no personal information is shown or was ever present "
    "in these specific rows.",
    icon="⚠️",
)
st.dataframe(
    anomalous_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "unit_price": st.column_config.NumberColumn("Unit price", format="£%.2f"),
        "line_revenue": st.column_config.NumberColumn("Line revenue", format="£%.2f"),
    },
)

st.markdown("#### Duplicate-candidate records")
st.write(
    f"**{format_count(int(metadata['duplicate_candidate_count']))}** rows "
    f"({100 * int(metadata['duplicate_candidate_count']) / total:.2f}% of all "
    f"records) are exact-duplicate candidates — preserved in every headline figure "
    f"on this dashboard by default, never silently removed."
)
st.caption(
    "Why preserve them: removing an exact duplicate risks discarding a genuine "
    "repeat purchase of the same product/quantity/price in the same session (e.g. "
    "a wholesale reseller); keeping them risks double-counting in a naive sum. "
    "Both are real possibilities this dataset alone cannot distinguish."
)

st.markdown("#### Duplicate sensitivity: complete dataset vs. deduplicated")
st.caption(
    "The 'deduplicated' comparison keeps the first occurrence per exact-match "
    "group and drops the rest — **it is not asserted as more accurate**, only "
    "shown as one possible sensitivity view."
)
metric_choice = st.selectbox(
    "Metric to compare", ["revenue", "units_sold", "average_order_value", "order_count"]
)
metric_label = metric_choice.replace("_", " ").title()
st.plotly_chart(
    duplicate_sensitivity_bars(sensitivity_df, metric_choice, metric_label),
    use_container_width=True,
)
complete = sensitivity_df[sensitivity_df["dataset_version"] == "complete_dataset"].iloc[0]
deduped = sensitivity_df[sensitivity_df["dataset_version"] == "deduplicated"].iloc[0]
if metric_choice in ("revenue", "average_order_value"):
    delta = format_currency(float(complete[metric_choice] - deduped[metric_choice]))
else:
    delta = format_count(int(complete[metric_choice] - deduped[metric_choice]))
st.caption(f"Difference (complete − deduplicated): {delta}")

render_footer()
