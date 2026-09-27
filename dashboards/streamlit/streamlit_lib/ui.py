"""Shared UI components. Formatting helpers are pure functions (testable without a
Streamlit runtime); the render_* functions call into Streamlit directly.
"""

from __future__ import annotations

import streamlit as st

from streamlit_lib.config import CASE_STUDY_URL, GITHUB_REPO_URL


def format_currency(value: float | None) -> str:
    if value is None:
        return "—"
    return f"£{value:,.2f}"


def format_percent(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}%"


def format_count(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


def render_reporting_period_banner(date_range_start: str, date_range_end: str) -> None:
    st.info(
        f"📅 **Historical data: {date_range_start} to {date_range_end}** — this is a "
        f"static, completed dataset, not a live feed. Refreshing this app re-reads "
        f"the same historical data; it does not fetch new transactions.",
        icon="📅",
    )


def render_partial_month_warning(context: str = "the selected period") -> None:
    st.warning(
        f"⚠️ **{context} includes an incomplete month.** The most recent month in "
        f"this dataset (December 2011) ends on the 9th, not the 30th/31st — its "
        f"month-over-month change is not a like-for-like comparison to a full month "
        f"and should not be read as an ordinary decline or growth figure.",
        icon="⚠️",
    )


def render_kpi_row(kpis: list[tuple[str, str, str | None]]) -> None:
    """kpis: list of (label, value, help_text)."""
    cols = st.columns(len(kpis))
    for col, (label, value, help_text) in zip(cols, kpis, strict=True):
        col.metric(label, value, help=help_text)


def render_footer() -> None:
    st.divider()
    links = []
    if GITHUB_REPO_URL:
        links.append(f"[GitHub repository]({GITHUB_REPO_URL})")
    else:
        links.append("GitHub repository — *link not yet configured (no remote pushed)*")
    if CASE_STUDY_URL:
        links.append(f"[Portfolio case study]({CASE_STUDY_URL})")
    else:
        links.append("Portfolio case study — *link not yet configured*")

    st.caption(
        " · ".join(links)
        + "\n\nData: UCI \"Online Retail\" dataset (CC BY 4.0), Daqing Chen, "
        "UCI Machine Learning Repository. Historical export, 2010-12-01 to "
        "2011-12-09 — not a live business feed."
    )


def render_empty_state(message: str) -> None:
    st.info(f"ℹ️ {message}")
