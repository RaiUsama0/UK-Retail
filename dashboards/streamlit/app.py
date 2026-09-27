"""UK E-commerce Sales & Customer Intelligence — public Streamlit demo.

Run locally with:  streamlit run dashboards/streamlit/app.py

Reads only from the committed, privacy-reviewed CSV extracts in
dashboards/streamlit/data/public/ — no PostgreSQL connection is used or required at
runtime. See dashboards/streamlit/README.md for how those extracts are generated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from streamlit_lib.config import APP_TITLE, PAGE_ICON  # noqa: E402
from streamlit_lib.data_loader import DataLoadError, load_table  # noqa: E402
from streamlit_lib.metrics import dataset_metadata_row  # noqa: E402
from streamlit_lib.ui import render_footer, render_reporting_period_banner  # noqa: E402

st.set_page_config(page_title=APP_TITLE, page_icon=PAGE_ICON, layout="wide")

st.title(f"{PAGE_ICON} {APP_TITLE}")

st.markdown(
    """
An analysis of a **historical** UK online gift retailer's transaction data
(UCI "Online Retail" dataset) — built as a full pipeline: SQL warehouse, verified
business intelligence, and this public demo. Every figure here traces back to a
reproducible SQL query; nothing is estimated.

**Use the sidebar to navigate:**
- **Executive Overview** — headline revenue, orders, and the monthly trend
- **Product Performance** — what actually drives revenue vs. volume, and two
  important caveats about the "top" products
- **Customer Intelligence** — repeat-purchase behaviour, spend concentration, and a
  clearly-labelled RFM segmentation heuristic
- **Transaction Quality** — how much of the data is an ordinary sale vs. a
  cancellation, a potential return, or something non-standard
"""
)

try:
    metadata = dataset_metadata_row(load_table("dataset_metadata"))
    render_reporting_period_banner(
        str(metadata["date_range_start"])[:10], str(metadata["date_range_end"])[:10]
    )
except DataLoadError as exc:
    st.error(
        f"⚠️ Could not load the public dataset: {exc}\n\n"
        f"If you're running this locally, generate it with `ingest-data export-public` "
        f"(requires a local PostgreSQL connection — see the main README)."
    )

st.markdown(
    """
### What this project demonstrates

A complete data pipeline: checksum-verified ingestion, a cleaning stage that
classifies every transaction rather than deleting anything ambiguous, an idempotent
PostgreSQL star schema, 19 SQL analytical views, a Power BI implementation
specification, and this Streamlit application — all documented and tested at every
stage. Full technical writeup: see the links below.
"""
)

render_footer()
