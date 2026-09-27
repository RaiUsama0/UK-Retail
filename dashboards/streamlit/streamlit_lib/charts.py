"""Plotly figure builders. Pure functions (dataframe in, Figure out) — no Streamlit
calls here, so a figure's data can be inspected in a test without a running app.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go

from streamlit_lib.config import STATUS_COLOURS


def monthly_revenue_trend(monthly_df, value_column: str = "net_revenue") -> go.Figure:
    """Line chart with partial months rendered as a distinct dashed/hollow marker —
    never visually identical to a complete month (see docs/kpi_definitions.md)."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=monthly_df["month_start"],
            y=monthly_df[value_column],
            mode="lines+markers",
            line={"color": STATUS_COLOURS["valid_sale"]},
            marker={
                "symbol": [
                    "circle-open" if p else "circle" for p in monthly_df["is_partial_month"]
                ],
                "size": 10,
                "line": {"width": 2},
            },
            name="Net revenue",
            hovertemplate="%{x|%b %Y}: £%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        yaxis_title="Net revenue (£)",
        xaxis_title=None,
        margin={"l": 40, "r": 20, "t": 20, "b": 20},
        showlegend=False,
    )
    return fig


def revenue_by_country_bar(country_df, top_n: int = 10) -> go.Figure:
    top = country_df.nsmallest(top_n, "revenue_rank").sort_values("net_revenue")
    fig = px.bar(
        top,
        x="net_revenue",
        y="country_name",
        orientation="h",
        color_discrete_sequence=[STATUS_COLOURS["valid_sale"]],
        labels={"net_revenue": "Net revenue (£)", "country_name": ""},
    )
    fig.update_traces(hovertemplate="%{y}: £%{x:,.2f}<extra></extra>")
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig


def top_products_bar(products_df, value_column: str, label: str) -> go.Figure:
    sorted_df = products_df.sort_values(value_column, ascending=True)
    fig = px.bar(
        sorted_df,
        x=value_column,
        y="description",
        orientation="h",
        color="is_non_merchandise" if "is_non_merchandise" in sorted_df.columns else None,
        color_discrete_map={
            True: STATUS_COLOURS["cancellation"], False: STATUS_COLOURS["valid_sale"]
        },
        labels={
            value_column: label, "description": "", "is_non_merchandise": "Non-merchandise"
        },
    )
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig


def product_revenue_contribution(products_df, top_n: int = 10) -> go.Figure:
    top = products_df.nsmallest(top_n, "revenue_rank").copy()
    other_pct = max(0.0, 100.0 - top["pct_of_total_revenue"].sum())
    labels = list(top["description"]) + (["All other products"] if other_pct > 0 else [])
    values = list(top["pct_of_total_revenue"]) + ([other_pct] if other_pct > 0 else [])
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.45))
    fig.update_traces(hovertemplate="%{label}: %{value:.2f}%<extra></extra>")
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig


def transaction_status_donut(quality_df) -> go.Figure:
    colours = [STATUS_COLOURS.get(s, "#9E9E9E") for s in quality_df["transaction_status"]]
    fig = go.Figure(
        go.Pie(
            labels=quality_df["transaction_status"],
            values=quality_df["row_count"],
            hole=0.5,
            marker={"colors": colours},
        )
    )
    fig.update_traces(hovertemplate="%{label}: %{value:,} rows (%{percent})<extra></extra>")
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig


def rfm_segment_bar(segment_df) -> go.Figure:
    sorted_df = segment_df.sort_values("avg_monetary", ascending=True)
    fig = px.bar(
        sorted_df,
        x="avg_monetary",
        y="rfm_segment_heuristic",
        orientation="h",
        color_discrete_sequence=[STATUS_COLOURS["valid_sale"]],
        labels={"avg_monetary": "Average spend (£)", "rfm_segment_heuristic": ""},
        text="customer_count",
    )
    fig.update_traces(
        texttemplate="%{text:,} customers", hovertemplate="%{y}: £%{x:,.2f} avg<extra></extra>"
    )
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig


def cohort_retention_heatmap(cohort_df) -> go.Figure:
    pivot = cohort_df.pivot(index="cohort_month", columns="month_index", values="retention_pct")
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=[f"M{i}" for i in pivot.columns],
            y=[d.strftime("%Y-%m") for d in pivot.index],
            colorscale="Greens",
            colorbar={"title": "Retention %"},
            hovertemplate="Cohort %{y}, %{x}: %{z:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(margin={"l": 20, "r": 20, "t": 20, "b": 20}, yaxis={"autorange": "reversed"})
    return fig


def duplicate_sensitivity_bars(sensitivity_df, metric_column: str, label: str) -> go.Figure:
    fig = px.bar(
        sensitivity_df,
        x="dataset_version",
        y=metric_column,
        color="dataset_version",
        color_discrete_sequence=[STATUS_COLOURS["valid_sale"], STATUS_COLOURS["non_standard"]],
        labels={metric_column: label, "dataset_version": ""},
    )
    fig.update_layout(showlegend=False, margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return fig
