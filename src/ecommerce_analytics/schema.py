"""Canonical structural schema for the raw Online Retail dataset.

This describes the dataset *as published* (see docs/data_dictionary.md) — column
names, dtypes, and nullability. It is intentionally silent on business rules such as
negative quantities or cancelled invoices; those are business-rule concerns handled in
``validation.py`` (non-fatal warnings) and, later, ``cleaning.py`` (Phase 3).
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera import Column

SHEET_NAME = "Online Retail"

# Canonical column order, exactly as published in the source file.
EXPECTED_COLUMNS: list[str] = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]

# Structural schema: column presence, dtype, and nullability only.
# `strict=False` so an unexpected extra column is reported as a data-quality warning
# elsewhere (validation.py) rather than a fatal schema error.
RAW_SCHEMA = pa.DataFrameSchema(
    {
        "InvoiceNo": Column(str, nullable=False, coerce=True),
        "StockCode": Column(str, nullable=False, coerce=True),
        "Description": Column(str, nullable=True, coerce=True),
        "Quantity": Column(int, nullable=False),
        "InvoiceDate": Column("datetime64[ns]", nullable=False),
        "UnitPrice": Column(float, nullable=False),
        "CustomerID": Column(float, nullable=True),
        "Country": Column(str, nullable=False, coerce=True),
    },
    strict=False,
    coerce=False,
)
