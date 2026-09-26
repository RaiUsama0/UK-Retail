import pytest

from ecommerce_analytics.profiling import compute_profile
from ecommerce_analytics.validation import SchemaValidationError, derive_warnings, validate_schema


def test_validate_schema_passes_on_valid_df(sample_df):
    validate_schema(sample_df)  # should not raise


def test_validate_schema_fails_on_missing_required_column(sample_df):
    broken = sample_df.drop(columns=["Quantity"])
    with pytest.raises(SchemaValidationError):
        validate_schema(broken)


def test_validate_schema_fails_on_wrong_dtype(sample_df):
    broken = sample_df.copy()
    broken["Quantity"] = broken["Quantity"].astype(str)
    with pytest.raises(SchemaValidationError):
        validate_schema(broken)


def test_derive_warnings_flags_expected_rules(sample_df):
    profile = compute_profile(sample_df)
    warnings = derive_warnings(profile)
    rules = {w.rule for w in warnings}

    assert "missing_customer_id" in rules
    assert "missing_description" in rules
    assert "duplicate_rows" in rules
    assert "negative_quantity" in rules
    assert "non_positive_unit_price" in rules
    assert "cancellations" in rules
    assert "potential_returns" in rules

    duplicate_warning = next(w for w in warnings if w.rule == "duplicate_rows")
    assert duplicate_warning.count == 1
    assert duplicate_warning.severity == "warning"

    missing_customer_warning = next(w for w in warnings if w.rule == "missing_customer_id")
    assert missing_customer_warning.severity == "info"
