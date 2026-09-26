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

from ecommerce_analytics.schema import RAW_SCHEMA


class SchemaValidationError(Exception):
    """Fatal structural validation failure (bad dtype, unexpected nulls, etc.)."""


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
