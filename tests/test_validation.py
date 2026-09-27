import pytest

from ecommerce_analytics.cleaning import clean_dataset, compute_cleaning_summary
from ecommerce_analytics.profiling import compute_profile
from ecommerce_analytics.validation import (
    CleaningValidationError,
    SchemaValidationError,
    derive_cleaning_warnings,
    derive_warnings,
    validate_cleaned_dataset,
    validate_schema,
)


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


def test_validate_cleaned_dataset_passes_on_correct_output(sample_df):
    cleaned = clean_dataset(sample_df)
    validate_cleaned_dataset(sample_df, cleaned)  # should not raise


def test_validate_cleaned_dataset_fails_on_row_count_mismatch(sample_df):
    cleaned = clean_dataset(sample_df).iloc[:-1]
    with pytest.raises(CleaningValidationError, match="Row count changed"):
        validate_cleaned_dataset(sample_df, cleaned)


def test_validate_cleaned_dataset_fails_on_broken_source_row_id(sample_df):
    cleaned = clean_dataset(sample_df).copy()
    cleaned["source_row_id"] = cleaned["source_row_id"] + 1  # no longer 0-based
    with pytest.raises(CleaningValidationError, match="source_row_id"):
        validate_cleaned_dataset(sample_df, cleaned)


def test_validate_cleaned_dataset_fails_on_unexpected_status(sample_df):
    cleaned = clean_dataset(sample_df).copy()
    cleaned["transaction_status"] = cleaned["transaction_status"].cat.add_categories(["bogus"])
    cleaned.loc[cleaned.index[0], "transaction_status"] = "bogus"
    with pytest.raises(CleaningValidationError, match="Unexpected transaction_status"):
        validate_cleaned_dataset(sample_df, cleaned)


def test_validate_cleaned_dataset_fails_on_inconsistent_line_revenue(sample_df):
    cleaned = clean_dataset(sample_df).copy()
    cleaned.loc[cleaned.index[0], "line_revenue"] = 999999.0
    with pytest.raises(CleaningValidationError, match="line_revenue is inconsistent"):
        validate_cleaned_dataset(sample_df, cleaned)


def test_derive_cleaning_warnings_flags_expected_rules(sample_df):
    cleaned = clean_dataset(sample_df)
    summary = compute_cleaning_summary(sample_df, cleaned)
    warnings = derive_cleaning_warnings(summary)
    rules = {w.rule for w in warnings}

    assert "non_standard_transactions" in rules
    assert "cancellation_exceptions" not in rules  # no exceptions in this fixture
    assert "duplicate_candidates" in rules

    duplicate_warning = next(w for w in warnings if w.rule == "duplicate_candidates")
    assert duplicate_warning.count == 2  # rows 0 and 7 in sample_df
