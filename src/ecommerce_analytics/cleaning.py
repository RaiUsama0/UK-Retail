"""Transforms the raw Online Retail dataframe into a deterministic, analysis-ready
dataset — normalised types, an explicit transaction classification, non-exclusive
business-rule flags, and decimal-safe revenue figures.

No row is ever added or removed here. Every input row maps to exactly one output row,
joined back to the raw file via ``source_row_id``. See ``docs/kpi_definitions.md`` for
the business rationale behind each rule, and ``docs/data_dictionary.md`` for the real,
verified counts this produces against the actual dataset.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# --- Transaction classification -------------------------------------------------
#
# Precedence (highest first) — a row gets exactly one status, decided in this order:
#   1. CANCELLATION      InvoiceNo starts with 'C' (the dataset's documented convention)
#   2. POTENTIAL_RETURN  Quantity < 0, not a cancellation
#   3. NON_STANDARD       Quantity >= 0, but UnitPrice <= 0, Quantity == 0, an invalid
#                          date, or an InvoiceNo that doesn't match the normal pattern
#   4. VALID_SALE         everything else: positive quantity, positive price, a
#                          normally-formatted invoice, not cancelled
#
# Cancellation takes precedence over potential-return so the two are never conflated
# (both are negative-quantity, but only one is a formally cancelled invoice). Potential
# return takes precedence over non-standard so that a negative-quantity row is never
# silently reclassified away from "potential_return" just because it also happens to
# carry a zero price — inspection of the real dataset shows *every* potential-return
# row has UnitPrice == 0 and no CustomerID (see docs/data_dictionary.md); that is a
# genuine characteristic of this category in this dataset, not grounds to relabel it.
STATUS_CANCELLATION = "cancellation"
STATUS_POTENTIAL_RETURN = "potential_return"
STATUS_NON_STANDARD = "non_standard"
STATUS_VALID_SALE = "valid_sale"
TRANSACTION_STATUSES = (
    STATUS_CANCELLATION,
    STATUS_POTENTIAL_RETURN,
    STATUS_NON_STANDARD,
    STATUS_VALID_SALE,
)

# A normal invoice number is 6 digits, optionally prefixed with 'C' for a cancellation.
# Verified against the real dataset: only 3 of 541,909 rows don't match this (a set of
# "Adjust bad debt" manual accounting entries with InvoiceNo like "A563185").
INVOICE_NO_PATTERN = re.compile(r"^C?\d{6}$")

# A normal product StockCode starts with a digit (5 digits, optionally with 1-2 trailing
# letters for a colour/variant suffix). Codes that don't — POST, DOT, M, D, S, C2, BANK
# CHARGES, AMAZONFEE, CRUK, DCGS*, gift_*, PADS, B — are administrative/non-product
# lines (postage, manual adjustments, carriage, samples, gift cards, discounts, etc.).
# This is an *informational* flag only: it does not change transaction_status, because
# many of these (e.g. POST) are genuine, correctly-priced charges that belong in revenue.
NON_PRODUCT_STOCK_CODE_PATTERN = re.compile(r"^\d")

MONEY_QUANTUM = Decimal("0.01")

CLEANED_COLUMNS = [
    "source_row_id",
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
    "transaction_status",
    "line_revenue",
    "flag_missing_customer_id",
    "flag_missing_description",
    "flag_non_positive_price",
    "flag_zero_quantity",
    "flag_duplicate_candidate",
    "flag_non_standard_invoice_format",
    "flag_non_standard_stock_code",
]

# Original columns compared when detecting exact-duplicate candidates. Deliberately
# excludes the technical `source_row_id`, which is unique per row by construction.
_DUPLICATE_SUBSET = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]

_COLUMN_RENAME_MAP = {
    "InvoiceNo": "invoice_no",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "UnitPrice": "unit_price",
    "CustomerID": "customer_id",
    "Country": "country",
}

# Same columns, under their final snake_case names — used once the dataframe has been
# renamed (see clean_dataset / compute_cleaning_summary).
_CLEANED_DUPLICATE_SUBSET = [_COLUMN_RENAME_MAP[c] for c in _DUPLICATE_SUBSET]


class CleaningError(Exception):
    """Raised when the cleaning pipeline itself cannot proceed (not a data-quality issue)."""


def _to_money(quantity: float, unit_price: float) -> float:
    """Multiply and round to whole pence using Decimal, avoiding float rounding modes.

    Converts via ``str()`` first so the Decimal is built from the value's decimal
    representation rather than its exact binary float64 representation.
    """
    q = Decimal(str(quantity))
    p = Decimal(str(unit_price))
    return float((q * p).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def normalise_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Fix dtypes and standardise text fields. Does not drop or reorder rows.

    - ``CustomerID`` becomes nullable ``Int64`` (was float64, forced off int by NaNs).
    - ``InvoiceDate`` is re-parsed defensively (``errors="coerce"``) so a genuinely
      invalid date becomes a detectable ``NaT`` rather than a silent bad value.
    - Text columns are stripped of leading/trailing whitespace. In the real dataset,
      113,452 ``Description`` values have such whitespace; other text columns have none,
      but are stripped defensively for any future data drop.
    """
    out = df.copy()

    out["InvoiceNo"] = out["InvoiceNo"].astype(str).str.strip()
    out["StockCode"] = out["StockCode"].astype(str).str.strip()
    out["Country"] = out["Country"].astype(str).str.strip()

    # "string" dtype (not object) so NA stays a proper missing value, not the literal "nan".
    out["Description"] = out["Description"].astype("string").str.strip()
    out.loc[out["Description"] == "", "Description"] = pd.NA

    out["CustomerID"] = out["CustomerID"].astype("Int64")
    out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")

    return out


def add_source_row_id(df: pd.DataFrame) -> pd.DataFrame:
    """Insert a deterministic technical row identifier: 0-based original row position.

    This is **not** a business transaction identifier — the raw file has none at the
    line-item grain. It exists purely to let every cleaned row be traced back to its
    exact position in the raw file, and is only stable for as long as that file's row
    order is unchanged (which ``ingestion.py``'s checksum verification guarantees).
    """
    out = df.reset_index(drop=True).copy()
    out.insert(0, "source_row_id", pd.RangeIndex(len(out)))
    return out


def classify_transactions(df: pd.DataFrame) -> pd.Series:
    """Assign exactly one ``transaction_status`` per row, per the precedence above."""
    invoice = df["InvoiceNo"].astype(str)
    is_cancelled = invoice.str.startswith("C")
    is_negative_qty = df["Quantity"] < 0
    is_non_standard_shape = (
        (df["UnitPrice"] <= 0)
        | (df["Quantity"] == 0)
        | df["InvoiceDate"].isna()
        | ~invoice.str.match(INVOICE_NO_PATTERN)
    )

    is_non_standard = ~is_cancelled & ~is_negative_qty & is_non_standard_shape

    status = pd.Series(STATUS_VALID_SALE, index=df.index, dtype="object")
    status = status.mask(is_non_standard, STATUS_NON_STANDARD)
    status = status.mask(~is_cancelled & is_negative_qty, STATUS_POTENTIAL_RETURN)
    status = status.mask(is_cancelled, STATUS_CANCELLATION)

    return status.astype(pd.CategoricalDtype(categories=TRANSACTION_STATUSES))


def compute_business_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add non-exclusive boolean flags. A row may carry any combination of these,
    independent of its primary ``transaction_status``."""
    out = df.copy()
    invoice = out["InvoiceNo"].astype(str)

    out["flag_missing_customer_id"] = out["CustomerID"].isna()
    out["flag_missing_description"] = out["Description"].isna()
    out["flag_non_positive_price"] = out["UnitPrice"] <= 0
    out["flag_zero_quantity"] = out["Quantity"] == 0
    out["flag_duplicate_candidate"] = out.duplicated(subset=_DUPLICATE_SUBSET, keep=False)
    out["flag_non_standard_invoice_format"] = ~invoice.str.match(INVOICE_NO_PATTERN)
    out["flag_non_standard_stock_code"] = ~out["StockCode"].astype(str).str.match(
        NON_PRODUCT_STOCK_CODE_PATTERN
    )

    return out


def compute_line_revenue(df: pd.DataFrame) -> pd.Series:
    """Quantity * UnitPrice per row, decimal-quantized to whole pence.

    Computed for every row regardless of status — it's a plain arithmetic fact, not a
    business judgement. Which statuses count toward gross/net revenue is defined in
    ``docs/kpi_definitions.md`` and applied at the reporting/reconciliation layer, not
    baked into this column.
    """
    return pd.Series(
        [
            _to_money(q, p)
            for q, p in zip(df["Quantity"].to_numpy(), df["UnitPrice"].to_numpy(), strict=True)
        ],
        index=df.index,
        dtype="float64",
    )


def clean_dataset(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Run the full, deterministic cleaning pipeline. Row count in == row count out."""
    logger.info("Cleaning %d raw rows", len(raw_df))

    df = add_source_row_id(raw_df)
    df = normalise_dtypes(df)
    df = compute_business_flags(df)
    df["transaction_status"] = classify_transactions(df)
    df["line_revenue"] = compute_line_revenue(df)

    df = df.rename(columns=_COLUMN_RENAME_MAP)

    df = df[CLEANED_COLUMNS]

    if len(df) != len(raw_df):
        raise CleaningError(
            f"Row count changed during cleaning: {len(raw_df)} raw rows -> {len(df)} "
            f"cleaned rows. Cleaning must never add or remove rows."
        )

    logger.info("Cleaning complete: %d rows, %d columns", *df.shape)
    return df


def _decimal_sum(quantities: pd.Series, unit_prices: pd.Series) -> Decimal:
    total = Decimal("0")
    for q, p in zip(quantities.to_numpy(), unit_prices.to_numpy(), strict=True):
        total += Decimal(str(q)) * Decimal(str(p))
    return total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_cleaning_summary(raw_df: pd.DataFrame, cleaned_df: pd.DataFrame) -> dict[str, Any]:
    """Compute every statistic for the cleaning report from the actual dataframes."""
    status_counts = cleaned_df["transaction_status"].value_counts()
    status_pct = cleaned_df["transaction_status"].value_counts(normalize=True) * 100

    is_cancelled = cleaned_df["transaction_status"] == STATUS_CANCELLATION
    is_return = cleaned_df["transaction_status"] == STATUS_POTENTIAL_RETURN
    is_non_standard = cleaned_df["transaction_status"] == STATUS_NON_STANDARD
    is_sale = cleaned_df["transaction_status"] == STATUS_VALID_SALE

    cancellation_exceptions = int((is_cancelled & (cleaned_df["quantity"] >= 0)).sum())

    gross_sales_revenue = _decimal_sum(
        cleaned_df.loc[is_sale, "quantity"], cleaned_df.loc[is_sale, "unit_price"]
    )
    cancellation_value = _decimal_sum(
        cleaned_df.loc[is_cancelled, "quantity"], cleaned_df.loc[is_cancelled, "unit_price"]
    )
    potential_return_value = _decimal_sum(
        cleaned_df.loc[is_return, "quantity"], cleaned_df.loc[is_return, "unit_price"]
    )
    non_standard_value = _decimal_sum(
        cleaned_df.loc[is_non_standard, "quantity"], cleaned_df.loc[is_non_standard, "unit_price"]
    )
    # Net revenue nets cancellations off gross sales. Potential returns and non-standard
    # rows are excluded on principle (see docs/kpi_definitions.md) — in this dataset
    # potential_return_value is exactly 0.00 anyway, since every such row is zero-priced.
    net_revenue = gross_sales_revenue + cancellation_value

    duplicate_groups = (
        cleaned_df[cleaned_df["flag_duplicate_candidate"]]
        .groupby(_CLEANED_DUPLICATE_SUBSET, dropna=False)
        .size()
    )

    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "row_count_raw": int(len(raw_df)),
        "row_count_cleaned": int(len(cleaned_df)),
        "transaction_status_counts": {k: int(v) for k, v in status_counts.items()},
        "transaction_status_pct": {k: round(float(v), 2) for k, v in status_pct.items()},
        "cancellation_exceptions": cancellation_exceptions,
        "invoice_format_exceptions": int(cleaned_df["flag_non_standard_invoice_format"].sum()),
        "flags": {
            "missing_customer_id": int(cleaned_df["flag_missing_customer_id"].sum()),
            "missing_description": int(cleaned_df["flag_missing_description"].sum()),
            "non_positive_price": int(cleaned_df["flag_non_positive_price"].sum()),
            "zero_quantity": int(cleaned_df["flag_zero_quantity"].sum()),
            "duplicate_candidate": int(cleaned_df["flag_duplicate_candidate"].sum()),
            "non_standard_stock_code": int(cleaned_df["flag_non_standard_stock_code"].sum()),
        },
        "duplicates": {
            "candidate_row_count": int(cleaned_df["flag_duplicate_candidate"].sum()),
            "distinct_group_count": int(len(duplicate_groups)),
            "largest_group_size": int(duplicate_groups.max()) if len(duplicate_groups) else 0,
        },
        "revenue": {
            "gross_sales_revenue": float(gross_sales_revenue),
            "cancellation_value": float(cancellation_value),
            "potential_return_value": float(potential_return_value),
            "non_standard_value": float(non_standard_value),
            "net_revenue": float(net_revenue),
        },
    }
    return summary


def render_cleaning_markdown(summary: dict[str, Any]) -> str:
    status_rows = "\n".join(
        f"| {status} | {count:,} | {summary['transaction_status_pct'].get(status, 0)}% |"
        for status, count in summary["transaction_status_counts"].items()
    )

    return f"""# Cleaning Summary Report

Generated: {summary['generated_at']}

## Row-count reconciliation

- Raw rows: **{summary['row_count_raw']:,}**
- Cleaned rows: **{summary['row_count_cleaned']:,}**
- Match: {"YES" if summary['row_count_raw'] == summary['row_count_cleaned'] else "NO — INVESTIGATE"}

## Transaction classification

| Status | Count | % of rows |
|---|---|---|
{status_rows}

- Cancellation-prefixed invoices with non-negative quantity (exceptions to the
  documented convention): **{summary['cancellation_exceptions']}**
- Rows with a non-standard InvoiceNo format (not `^C?\\d{{6}}$`): \
**{summary['invoice_format_exceptions']}**

## Business-rule flags (non-exclusive — a row may carry several)

- Missing CustomerID: {summary['flags']['missing_customer_id']:,}
- Missing Description: {summary['flags']['missing_description']:,}
- Non-positive UnitPrice: {summary['flags']['non_positive_price']:,}
- Zero Quantity: {summary['flags']['zero_quantity']:,}
- Duplicate candidates: {summary['flags']['duplicate_candidate']:,}
- Non-standard (non-product) StockCode: {summary['flags']['non_standard_stock_code']:,}

## Duplicate candidates

- Rows flagged as a duplicate candidate: **{summary['duplicates']['candidate_row_count']:,}**
- Distinct duplicate groups: **{summary['duplicates']['distinct_group_count']:,}**
- Largest single duplicate group: **{summary['duplicates']['largest_group_size']}** identical rows
- Policy: duplicates are preserved, never auto-dropped. Removing them risks deleting a
  genuine repeat purchase of the same product/quantity/price in the same session;
  keeping them risks double-counting in naive aggregations. The
  `flag_duplicate_candidate` column lets each downstream query choose deliberately.

## Revenue (GBP, decimal-safe summation to avoid float accumulation drift)

- Gross sales revenue (valid_sale rows only): \
**£{summary['revenue']['gross_sales_revenue']:,.2f}**
- Cancellation value (cancellation rows; always <= 0): \
**£{summary['revenue']['cancellation_value']:,.2f}**
- Potential return value (potential_return rows): \
**£{summary['revenue']['potential_return_value']:,.2f}**
- Non-standard value (non_standard rows, excluded from net revenue): \
**£{summary['revenue']['non_standard_value']:,.2f}**
- **Net revenue** (gross sales + cancellation value): \
**£{summary['revenue']['net_revenue']:,.2f}**

No profit, margin, or shipping cost figures are calculated — the source dataset does
not contain the data required for them.
"""


def save_cleaning_reports(summary: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    import json

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown_path.write_text(render_cleaning_markdown(summary), encoding="utf-8")


def save_cleaned_dataset(cleaned_df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_df.to_parquet(path, index=False)
    logger.info("Wrote cleaned dataset to %s (%d rows)", path, len(cleaned_df))
