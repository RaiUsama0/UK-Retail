from ecommerce_analytics.profiling import compute_profile, render_markdown


def test_compute_profile_known_stats(sample_df):
    profile = compute_profile(sample_df)

    assert profile["row_count"] == 8
    assert profile["column_count"] == 8
    assert profile["unexpected_columns"] == []

    assert profile["missing_values"]["Description"] == 1
    assert profile["missing_values"]["CustomerID"] == 2

    assert profile["duplicate_rows"] == 1

    assert profile["unique_invoice_count"] == 7
    assert profile["unique_customer_count"] == 3
    assert profile["unique_product_count"] == 5
    assert profile["unique_country_count"] == 4

    assert profile["invoice_date_min"].startswith("2011-01-01")
    assert profile["invoice_date_max"].startswith("2011-01-07")

    assert profile["quantity"]["negative_count"] == 2
    assert profile["quantity"]["zero_count"] == 0

    assert profile["unit_price"]["zero_count"] == 1
    assert profile["unit_price"]["negative_count"] == 0

    assert profile["cancellations_and_returns"]["cancellation_count"] == 1
    assert profile["cancellations_and_returns"]["potential_return_count"] == 1

    assert profile["country_distribution"]["United Kingdom"] == 4
    assert profile["identifier_coverage"]["customer_id_present_count"] == 6


def test_render_markdown_contains_key_figures(sample_df):
    profile = compute_profile(sample_df)
    markdown = render_markdown(profile)

    assert "Data Profiling Report" in markdown
    assert "8" in markdown  # row count appears somewhere
    assert "United Kingdom" in markdown
