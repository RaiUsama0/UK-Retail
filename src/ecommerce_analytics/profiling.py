"""Data profiling: computes every statistic from the actual loaded dataset (no
fabricated or assumed figures) and renders it as JSON and Markdown reports.

This module only *observes* the data — it never removes or modifies rows. Business-
rule interpretation of these numbers (fatal vs. warning) lives in ``validation.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ecommerce_analytics.schema import EXPECTED_COLUMNS


def compute_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Compute the full profiling report as a JSON-serialisable dict."""
    row_count = len(df)

    is_cancelled = df["InvoiceNo"].astype(str).str.startswith("C")
    negative_qty = df["Quantity"] < 0
    zero_qty = df["Quantity"] == 0
    negative_price = df["UnitPrice"] < 0
    zero_price = df["UnitPrice"] == 0

    # "Potential returns": negative-quantity rows NOT flagged as a cancellation by
    # InvoiceNo prefix — kept distinct from true cancellations, per kpi_definitions.md.
    potential_returns = negative_qty & ~is_cancelled

    country_counts = df["Country"].value_counts(dropna=False)

    profile: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "row_count": row_count,
        "column_count": int(df.shape[1]),
        "columns": [{"name": col, "dtype": str(df[col].dtype)} for col in df.columns],
        "unexpected_columns": [c for c in df.columns if c not in EXPECTED_COLUMNS],
        "missing_values": {col: int(df[col].isna().sum()) for col in df.columns},
        "missing_values_pct": {
            col: round(float(df[col].isna().mean()) * 100, 2) for col in df.columns
        },
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_rows_pct": round(float(df.duplicated().mean()) * 100, 2),
        "unique_invoice_count": int(df["InvoiceNo"].nunique()),
        "unique_customer_count": int(df["CustomerID"].nunique()),
        "unique_product_count": int(df["StockCode"].nunique()),
        "unique_country_count": int(df["Country"].nunique()),
        "invoice_date_min": df["InvoiceDate"].min().isoformat(),
        "invoice_date_max": df["InvoiceDate"].max().isoformat(),
        "quantity": {
            "min": float(df["Quantity"].min()),
            "max": float(df["Quantity"].max()),
            "negative_count": int(negative_qty.sum()),
            "zero_count": int(zero_qty.sum()),
        },
        "unit_price": {
            "min": float(df["UnitPrice"].min()),
            "max": float(df["UnitPrice"].max()),
            "negative_count": int(negative_price.sum()),
            "zero_count": int(zero_price.sum()),
        },
        "cancellations_and_returns": {
            "cancellation_count": int(is_cancelled.sum()),
            "cancellation_pct_of_rows": round(float(is_cancelled.mean()) * 100, 2),
            "potential_return_count": int(potential_returns.sum()),
        },
        "country_distribution": {
            (str(k) if pd.notna(k) else "(missing)"): int(v)
            for k, v in country_counts.items()
        },
        "identifier_coverage": {
            "customer_id_present_count": int(df["CustomerID"].notna().sum()),
            "customer_id_present_pct": round(float(df["CustomerID"].notna().mean()) * 100, 2),
            "stock_code_present_count": int(df["StockCode"].notna().sum()),
            "stock_code_present_pct": round(float(df["StockCode"].notna().mean()) * 100, 2),
        },
    }
    return profile


def render_markdown(profile: dict[str, Any]) -> str:
    top_countries = list(profile["country_distribution"].items())[:15]
    top_countries_table = "\n".join(f"| {c} | {n:,} |" for c, n in top_countries)
    missing_table = "\n".join(
        f"| {col} | {profile['missing_values'][col]:,} | {profile['missing_values_pct'][col]}% |"
        for col in profile["missing_values"]
    )
    columns_table = "\n".join(
        f"| {c['name']} | {c['dtype']} |" for c in profile["columns"]
    )

    return f"""# Data Profiling Report

Generated: {profile['generated_at']}

## Overview

- Total records: **{profile['row_count']:,}**
- Total columns: **{profile['column_count']}**
- Unexpected columns beyond the documented schema: {profile['unexpected_columns'] or 'none'}

## Columns

| Column | Dtype |
|---|---|
{columns_table}

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
{missing_table}

## Duplicates

- Fully duplicated rows: **{profile['duplicate_rows']:,}** ({profile['duplicate_rows_pct']}%)

## Identifiers

- Unique invoices: **{profile['unique_invoice_count']:,}**
- Unique customers: **{profile['unique_customer_count']:,}**
- Unique products (StockCode): **{profile['unique_product_count']:,}**
- Unique countries: **{profile['unique_country_count']:,}**
- CustomerID present: {profile['identifier_coverage']['customer_id_present_count']:,} \
rows ({profile['identifier_coverage']['customer_id_present_pct']}%)
- StockCode present: {profile['identifier_coverage']['stock_code_present_count']:,} \
rows ({profile['identifier_coverage']['stock_code_present_pct']}%)

## Invoice date range

- Minimum: {profile['invoice_date_min']}
- Maximum: {profile['invoice_date_max']}

## Quantity

- Range: {profile['quantity']['min']:,.0f} to {profile['quantity']['max']:,.0f}
- Negative quantity rows: {profile['quantity']['negative_count']:,}
- Zero quantity rows: {profile['quantity']['zero_count']:,}

## Unit price

- Range: {profile['unit_price']['min']:,.2f} to {profile['unit_price']['max']:,.2f}
- Negative price rows: {profile['unit_price']['negative_count']:,}
- Zero price rows: {profile['unit_price']['zero_count']:,}

## Cancellations and returns

- Cancellations (InvoiceNo starts with 'C'): \
{profile['cancellations_and_returns']['cancellation_count']:,} \
({profile['cancellations_and_returns']['cancellation_pct_of_rows']}% of rows)
- Potential returns (negative quantity, not flagged as a cancellation): \
{profile['cancellations_and_returns']['potential_return_count']:,}

## Country distribution (top 15)

| Country | Rows |
|---|---|
{top_countries_table}
"""


def save_reports(profile: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(profile), encoding="utf-8")
