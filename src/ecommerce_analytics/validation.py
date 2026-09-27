"""Two distinct kinds of validation, kept deliberately separate:

1. **Schema validation** (fatal) — column presence, dtypes, nullability. A failure
   here means the file structurally isn't the dataset we expect, and ingestion must
   stop.
2. **Business-rule validation** (non-fatal) — negative quantities, cancelled
   invoices, missing customer IDs, etc. These are real, expected business events in
   this dataset, not defects, so they are recorded as warnings for visibility rather
   than causing ingestion to fail. Phase 3 (``cleaning.py``) is where they get acted
   upon (classified into sale / cancellation / return / questionable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandera.errors import SchemaErrors

from ecommerce_analytics.cleaning import TRANSACTION_STATUSES
from ecommerce_analytics.schema import RAW_SCHEMA


class SchemaValidationError(Exception):
    """Fatal structural validation failure (bad dtype, unexpected nulls, etc.)."""


class CleaningValidationError(Exception):
    """Fatal post-cleaning validation failure — a regression guard, not a data-quality
    finding. If this ever fires, ``cleaning.py`` itself has a bug."""


@dataclass(frozen=True)
class DataQualityWarning:
    rule: str
    count: int
    severity: str  # "info" | "warning"
    message: str


def validate_schema(df: pd.DataFrame) -> None:
    """Raise :class:`SchemaValidationError` if the dataframe fails structural checks."""
    try:
        RAW_SCHEMA.validate(df, lazy=True)
    except SchemaErrors as exc:
        failures = exc.failure_cases[["column", "check", "failure_case"]].to_dict(
            orient="records"
        )
        raise SchemaValidationError(
            f"Schema validation failed with {len(failures)} failure(s): {failures}"
        ) from exc


def derive_warnings(profile: dict[str, Any]) -> list[DataQualityWarning]:
    """Translate profiling statistics into business-rule warnings. Pure function —
    does not recompute anything, so profiling only ever runs once per pipeline run."""
    warnings: list[DataQualityWarning] = []

    missing_customer = profile["missing_values"]["CustomerID"]
    if missing_customer:
        warnings.append(
            DataQualityWarning(
                rule="missing_customer_id",
                count=missing_customer,
                severity="info",
                message=(
                    f"{missing_customer:,} rows "
                    f"({profile['missing_values_pct']['CustomerID']}%) have no "
                    "CustomerID. Not necessarily invalid transactions — excluded from "
                    "customer-level KPIs only (see docs/kpi_definitions.md)."
                ),
            )
        )

    missing_description = profile["missing_values"]["Description"]
    if missing_description:
        warnings.append(
            DataQualityWarning(
                rule="missing_description",
                count=missing_description,
                severity="info",
                message=f"{missing_description:,} rows have no Description.",
            )
        )

    if profile["duplicate_rows"]:
        warnings.append(
            DataQualityWarning(
                rule="duplicate_rows",
                count=profile["duplicate_rows"],
                severity="warning",
                message=(
                    f"{profile['duplicate_rows']:,} fully duplicated rows "
                    f"({profile['duplicate_rows_pct']}%)."
                ),
            )
        )

    neg_qty = profile["quantity"]["negative_count"]
    if neg_qty:
        warnings.append(
            DataQualityWarning(
                rule="negative_quantity",
                count=neg_qty,
                severity="info",
                message=(
                    f"{neg_qty:,} rows have negative Quantity — expected for "
                    "cancellations/returns, not treated as invalid."
                ),
            )
        )

    zero_qty = profile["quantity"]["zero_count"]
    if zero_qty:
        warnings.append(
            DataQualityWarning(
                rule="zero_quantity",
                count=zero_qty,
                severity="warning",
                message=f"{zero_qty:,} rows have Quantity = 0.",
            )
        )

    non_positive_price = (
        profile["unit_price"]["negative_count"] + profile["unit_price"]["zero_count"]
    )
    if non_positive_price:
        warnings.append(
            DataQualityWarning(
                rule="non_positive_unit_price",
                count=non_positive_price,
                severity="warning",
                message=(
                    f"{non_positive_price:,} rows have UnitPrice <= 0 — likely "
                    "adjustments, not genuine product sales."
                ),
            )
        )

    cancellations = profile["cancellations_and_returns"]["cancellation_count"]
    if cancellations:
        warnings.append(
            DataQualityWarning(
                rule="cancellations",
                count=cancellations,
                severity="info",
                message=f"{cancellations:,} rows are cancellations (InvoiceNo starts with 'C').",
            )
        )

    potential_returns = profile["cancellations_and_returns"]["potential_return_count"]
    if potential_returns:
        warnings.append(
            DataQualityWarning(
                rule="potential_returns",
                count=potential_returns,
                severity="warning",
                message=(
                    f"{potential_returns:,} rows have negative Quantity but are not "
                    "flagged as a cancellation by InvoiceNo — flagged for review."
                ),
            )
        )

    if profile["unexpected_columns"]:
        warnings.append(
            DataQualityWarning(
                rule="unexpected_columns",
                count=len(profile["unexpected_columns"]),
                severity="warning",
                message=f"Unexpected columns present: {profile['unexpected_columns']}.",
            )
        )

    return warnings


def validate_cleaned_dataset(raw_df: pd.DataFrame, cleaned_df: pd.DataFrame) -> None:
    """Fatal regression guards over the *cleaning* step's own invariants.

    These should never fire if ``cleaning.py`` is correct — they exist to catch a
    future bug (e.g. a row silently dropped, a status left unset, a monetary
    calculation drifting from its inputs), not to flag business data-quality issues.
    """
    errors: list[str] = []

    if len(cleaned_df) != len(raw_df):
        errors.append(
            f"Row count changed: {len(raw_df)} raw rows vs {len(cleaned_df)} cleaned rows."
        )

    expected_ids = pd.RangeIndex(len(cleaned_df))
    if not cleaned_df["source_row_id"].equals(pd.Series(expected_ids, name="source_row_id")):
        errors.append(
            "source_row_id is not a contiguous 0..N-1 range — technical identifier is broken."
        )

    unexpected_statuses = set(cleaned_df["transaction_status"].dropna().unique()) - set(
        TRANSACTION_STATUSES
    )
    if unexpected_statuses:
        errors.append(f"Unexpected transaction_status values: {unexpected_statuses}")
    if cleaned_df["transaction_status"].isna().any():
        errors.append(
            f"{cleaned_df['transaction_status'].isna().sum()} rows have no transaction_status."
        )

    status_counts_sum = cleaned_df["transaction_status"].value_counts().sum()
    if status_counts_sum != len(cleaned_df):
        errors.append(
            f"transaction_status counts sum to {status_counts_sum}, expected {len(cleaned_df)}."
        )

    recomputed = (cleaned_df["quantity"] * cleaned_df["unit_price"]).round(2)
    mismatch = (recomputed - cleaned_df["line_revenue"]).abs() > 0.01
    if mismatch.any():
        errors.append(
            f"line_revenue is inconsistent with quantity * unit_price on "
            f"{int(mismatch.sum())} row(s)."
        )

    if errors:
        raise CleaningValidationError("; ".join(errors))


def derive_cleaning_warnings(summary: dict[str, Any]) -> list[DataQualityWarning]:
    """Business-rule warnings derived from the cleaning summary. Pure function — does
    not recompute anything, mirroring ``derive_warnings`` for the raw profile."""
    warnings: list[DataQualityWarning] = []

    non_standard = summary["transaction_status_counts"].get("non_standard", 0)
    if non_standard:
        warnings.append(
            DataQualityWarning(
                rule="non_standard_transactions",
                count=non_standard,
                severity="warning",
                message=(
                    f"{non_standard:,} rows classified non_standard "
                    f"({summary['transaction_status_pct'].get('non_standard', 0)}% of rows) — "
                    "non-positive price, zero quantity, invalid date, or anomalous "
                    "InvoiceNo format. Excluded from net revenue."
                ),
            )
        )

    potential_return = summary["transaction_status_counts"].get("potential_return", 0)
    if potential_return:
        warnings.append(
            DataQualityWarning(
                rule="potential_return_zero_value",
                count=potential_return,
                severity="info",
                message=(
                    f"{potential_return:,} potential_return rows carry a combined "
                    f"revenue value of £{summary['revenue']['potential_return_value']:,.2f} "
                    "in this dataset (every such row has UnitPrice = 0) — not confirmed "
                    "monetary refunds, and excluded from net revenue on that basis."
                ),
            )
        )

    if summary["cancellation_exceptions"]:
        warnings.append(
            DataQualityWarning(
                rule="cancellation_exceptions",
                count=summary["cancellation_exceptions"],
                severity="warning",
                message=(
                    f"{summary['cancellation_exceptions']} cancellation-prefixed invoices "
                    "have non-negative Quantity — exception to the documented convention."
                ),
            )
        )

    if summary["invoice_format_exceptions"]:
        warnings.append(
            DataQualityWarning(
                rule="non_standard_invoice_format",
                count=summary["invoice_format_exceptions"],
                severity="warning",
                message=(
                    f"{summary['invoice_format_exceptions']} rows have an InvoiceNo not "
                    "matching the normal ^C?\\d{6}$ pattern."
                ),
            )
        )

    duplicate_count = summary["duplicates"]["candidate_row_count"]
    if duplicate_count:
        warnings.append(
            DataQualityWarning(
                rule="duplicate_candidates",
                count=duplicate_count,
                severity="warning",
                message=(
                    f"{duplicate_count:,} rows across "
                    f"{summary['duplicates']['distinct_group_count']:,} groups are exact-"
                    f"duplicate candidates (largest group: "
                    f"{summary['duplicates']['largest_group_size']} rows). Preserved, not "
                    "dropped — see cleaning report for the retention-vs-removal trade-off."
                ),
            )
        )

    non_standard_stock = summary["flags"]["non_standard_stock_code"]
    if non_standard_stock:
        warnings.append(
            DataQualityWarning(
                rule="non_standard_stock_code",
                count=non_standard_stock,
                severity="info",
                message=(
                    f"{non_standard_stock:,} rows have a non-product StockCode "
                    "(e.g. POST, DOT, M, BANK CHARGES) — informational only, does not "
                    "affect transaction_status."
                ),
            )
        )

    return warnings
