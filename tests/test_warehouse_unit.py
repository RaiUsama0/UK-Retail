"""Unit tests for warehouse.py that don't require a database connection."""

from decimal import Decimal

import pandas as pd

from ecommerce_analytics.warehouse import STAGING_COLUMNS, _decimal_sum, _to_copy_buffer


def test_staging_columns_matches_cleaning_columns():
    from ecommerce_analytics.cleaning import CLEANED_COLUMNS

    assert STAGING_COLUMNS == CLEANED_COLUMNS


def test_to_copy_buffer_orders_columns_and_has_no_header():
    df = pd.DataFrame({col: [1] for col in STAGING_COLUMNS})
    buf = _to_copy_buffer(df)
    first_line = buf.splitlines()[0]
    assert first_line == ",".join("1" for _ in STAGING_COLUMNS)


def test_to_copy_buffer_renders_missing_values_as_empty_string():
    df = pd.DataFrame({col: [None] for col in STAGING_COLUMNS})
    buf = _to_copy_buffer(df)
    first_line = buf.splitlines()[0]
    assert first_line == ",".join("" for _ in STAGING_COLUMNS)


def test_to_copy_buffer_reorders_even_if_input_columns_are_shuffled():
    shuffled = list(reversed(STAGING_COLUMNS))
    df = pd.DataFrame({col: [i] for i, col in enumerate(shuffled)})
    buf = _to_copy_buffer(df)
    values = buf.splitlines()[0].split(",")
    for col, value in zip(STAGING_COLUMNS, values, strict=True):
        assert str(shuffled.index(col)) == value


def test_decimal_sum_known_values():
    quantities = pd.Series([2, 3, -1])
    prices = pd.Series([2.5, 1.0, 5.0])
    # (2*2.5) + (3*1.0) + (-1*5.0) = 5.0 + 3.0 - 5.0 = 3.0
    assert _decimal_sum(quantities, prices) == Decimal("3.00")


def test_decimal_sum_avoids_float_drift_over_many_rows():
    # 0.1 repeated many times famously drifts under naive float summation.
    quantities = pd.Series([1] * 1000)
    prices = pd.Series([0.1] * 1000)
    assert _decimal_sum(quantities, prices) == Decimal("100.00")
