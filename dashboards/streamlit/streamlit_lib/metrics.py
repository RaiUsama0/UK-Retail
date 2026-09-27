"""Pure metric-calculation functions — no Streamlit imports, so these are directly
unit-testable. Every function documents exactly what it can and cannot be filtered
by, given the public dataset's grain (see dashboards/streamlit/README.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def safe_divide(numerator: float, denominator: float) -> float | None:
    """DIVIDE-safe helper: None (rendered as "—") instead of a ZeroDivisionError or inf."""
    if denominator in (0, None) or pd.isna(denominator):
        return None
    return numerator / denominator


@dataclass(frozen=True)
class HeadlineKPIs:
    gross_sales_revenue: float
    cancellation_value: float
    net_revenue: float
    order_count: int
    average_order_value: float | None
    months_included: int
    has_partial_month: bool


def filter_monthly_revenue_by_date(
    monthly_df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp
) -> pd.DataFrame:
    """Subset monthly_revenue.csv to months whose start falls within [start, end].
    This is the ONLY correct way to apply a date filter in this app — there is no
    transaction-level data available to re-aggregate from directly (see the public
    dataset's privacy design in dashboards/streamlit/data/public/README.md)."""
    mask = (monthly_df["month_start"] >= start_date) & (monthly_df["month_start"] <= end_date)
    return monthly_df.loc[mask]


def compute_headline_kpis(monthly_df: pd.DataFrame) -> HeadlineKPIs:
    """Recomputes net revenue / orders / AOV by summing the (possibly date-filtered)
    monthly_revenue rows — a genuine recalculation from suitable underlying data, not
    a full-dataset figure silently mislabelled as filtered."""
    gross = float(monthly_df["gross_sales_revenue"].sum())
    cancel = float(monthly_df["cancellation_value"].sum())
    net = gross + cancel
    orders = int(monthly_df["order_count"].sum())
    aov = safe_divide(net, orders)
    return HeadlineKPIs(
        gross_sales_revenue=gross,
        cancellation_value=cancel,
        net_revenue=net,
        order_count=orders,
        average_order_value=aov,
        months_included=len(monthly_df),
        has_partial_month=bool(monthly_df["is_partial_month"].any()),
    )


def top_products_from_monthly_trend(
    trend_df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp, top_n: int = 10
) -> pd.DataFrame:
    """Recomputes a product ranking for a selected date range from the per-product,
    per-month trend data — used whenever the user's date filter differs from the full
    dataset range, so the ranking genuinely reflects the selected period rather than
    silently showing the whole-dataset ranking under a filtered-looking UI."""
    month_start = pd.to_datetime(
        trend_df["year"].astype(str) + "-" + trend_df["month"].astype(str) + "-01"
    )
    mask = (month_start >= start_date) & (month_start <= end_date)
    subset = trend_df.loc[mask]

    grouped = (
        subset.groupby(["stock_code", "description"], as_index=False)
        .agg(units_sold=("units_sold", "sum"), revenue=("revenue", "sum"))
        .sort_values("revenue", ascending=False)
    )
    return grouped.head(top_n)


def customer_headline_row(headline_df: pd.DataFrame) -> dict:
    """headline_df is customer_headline_metrics.csv — always exactly one row, and
    always a full-dataset figure (no date/country dimension exists at this grain in
    the public dataset)."""
    return headline_df.iloc[0].to_dict()


def dataset_metadata_row(metadata_df: pd.DataFrame) -> dict:
    return metadata_df.iloc[0].to_dict()


def filter_product_country_performance(
    df: pd.DataFrame, countries: list[str] | None
) -> pd.DataFrame:
    if not countries:
        return df
    return df[df["country_name"].isin(countries)]


def filter_by_column_values(
    df: pd.DataFrame, column: str, values: list[str] | None
) -> pd.DataFrame:
    if not values:
        return df
    return df[df[column].isin(values)]
