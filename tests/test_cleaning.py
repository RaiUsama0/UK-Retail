import pandas as pd
import pytest

from ecommerce_analytics.cleaning import (
    CleaningError,
    clean_dataset,
    compute_cleaning_summary,
)

# A hand-crafted dataset covering every transaction_status and flag combination, with
# hand-computed expected results (see the row-by-row comments). Row H is an exact
# duplicate of row A. Row G has an invalid (NaT) InvoiceDate.
_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]

_ROWS = [
    # A: ordinary valid sale
    ("600001", "10001", "WIDGET A", 5, "2011-02-01", 2.0, 2001.0, "United Kingdom"),
    # B: cancellation, negative quantity (matches the documented convention)
    ("C600002", "10001", "WIDGET A", -3, "2011-02-02", 2.0, 2001.0, "United Kingdom"),
    # C: cancellation, POSITIVE quantity -- an exception to the usual convention
    ("C600003", "10002", "WIDGET B", 2, "2011-02-03", 3.0, 2002.0, "France"),
    # D: potential return -- negative quantity, no cancellation prefix, zero price
    ("600004", "10003", "WIDGET C", -4, "2011-02-04", 0.0, None, "Germany"),
    # E: non-standard -- zero price, positive quantity, missing description
    ("600005", "10004", None, 2, "2011-02-05", 0.0, None, "Spain"),
    # F: non-standard -- anomalous InvoiceNo format, despite a positive price/quantity
    ("A600006", "10005", "ADJUSTMENT", 1, "2011-02-06", 50.0, None, "United Kingdom"),
    # G: non-standard -- invalid (missing) InvoiceDate
    ("600007", "10006", "WIDGET G", 1, None, 10.0, 2003.0, "United Kingdom"),
    # H: exact duplicate of row A
    ("600001", "10001", "WIDGET A", 5, "2011-02-01", 2.0, 2001.0, "United Kingdom"),
    # I: valid sale, but a non-product (non-standard) StockCode
    ("600008", "POST", "Postage", 1, "2011-02-08", 15.0, 2004.0, "United Kingdom"),
    # J: valid sale, missing CustomerID only
    ("600009", "10007", "WIDGET J", 3, "2011-02-09", 5.0, None, "United Kingdom"),
]


@pytest.fixture
def classification_df() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return df


@pytest.fixture
def cleaned(classification_df) -> pd.DataFrame:
    return clean_dataset(classification_df)


def test_row_count_preserved(classification_df, cleaned):
    assert len(cleaned) == len(classification_df) == 10


def test_source_row_id_is_deterministic_position(cleaned):
    assert cleaned["source_row_id"].tolist() == list(range(10))


def test_transaction_status_classification(cleaned):
    statuses = cleaned["transaction_status"].tolist()
    expected = [
        "valid_sale",  # A
        "cancellation",  # B
        "cancellation",  # C (exception: positive quantity)
        "potential_return",  # D
        "non_standard",  # E
        "non_standard",  # F
        "non_standard",  # G
        "valid_sale",  # H (duplicate of A)
        "valid_sale",  # I
        "valid_sale",  # J
    ]
    assert statuses == expected


def test_negative_quantity_not_all_classified_as_return(cleaned):
    # B and C are both cancellation-prefixed with different quantity signs; D is the
    # only true "potential_return". Negative quantity alone must not drive the status.
    negative_qty_statuses = set(
        cleaned.loc[cleaned["quantity"] < 0, "transaction_status"].tolist()
    )
    assert negative_qty_statuses == {"cancellation", "potential_return"}


def test_flags_are_independent_of_primary_status(cleaned):
    row_i = cleaned.loc[cleaned["invoice_no"] == "600008"].iloc[0]
    assert row_i["transaction_status"] == "valid_sale"
    assert row_i["flag_non_standard_stock_code"]  # flagged, but still a valid sale

    row_j = cleaned.loc[cleaned["invoice_no"] == "600009"].iloc[0]
    assert row_j["transaction_status"] == "valid_sale"
    assert row_j["flag_missing_customer_id"]


def test_duplicate_candidates_flagged_not_dropped(classification_df, cleaned):
    assert len(cleaned) == len(classification_df)  # nothing removed
    assert cleaned["flag_duplicate_candidate"].sum() == 2  # rows A and H
    dup_rows = cleaned[cleaned["flag_duplicate_candidate"]]
    assert set(dup_rows["source_row_id"]) == {0, 7}


def test_decimal_safe_line_revenue(cleaned):
    expected = {
        0: 10.0,  # A: 5 * 2.0
        1: -6.0,  # B: -3 * 2.0
        2: 6.0,  # C: 2 * 3.0
        3: 0.0,  # D: -4 * 0.0
        4: 0.0,  # E: 2 * 0.0
        5: 50.0,  # F: 1 * 50.0
        6: 10.0,  # G: 1 * 10.0
        7: 10.0,  # H: duplicate of A
        8: 15.0,  # I: 1 * 15.0
        9: 15.0,  # J: 3 * 5.0
    }
    for row_id, expected_revenue in expected.items():
        actual = cleaned.loc[cleaned["source_row_id"] == row_id, "line_revenue"].iloc[0]
        assert actual == pytest.approx(expected_revenue)


def test_missing_value_flags(cleaned):
    assert cleaned["flag_missing_customer_id"].sum() == 4  # D, E, F, J
    assert cleaned["flag_missing_description"].sum() == 1  # E


def test_non_positive_price_flag(cleaned):
    # D and E both have UnitPrice == 0; F has a positive price so is NOT flagged here
    # even though it's non_standard for a different reason (invoice format).
    assert cleaned["flag_non_positive_price"].sum() == 2


def test_non_standard_invoice_format_flag(cleaned):
    assert cleaned["flag_non_standard_invoice_format"].sum() == 1
    flagged = cleaned.loc[cleaned["flag_non_standard_invoice_format"], "invoice_no"].tolist()
    assert flagged == ["A600006"]


def test_repeatable_execution_is_deterministic(classification_df):
    first = clean_dataset(classification_df)
    second = clean_dataset(classification_df)
    pd.testing.assert_frame_equal(first, second)


def test_clean_dataset_raises_on_row_count_change(classification_df, monkeypatch):
    import ecommerce_analytics.cleaning as cleaning_module

    original_add_id = cleaning_module.add_source_row_id

    def _broken_add_id(df):
        return original_add_id(df).iloc[:-1]  # silently drop a row

    monkeypatch.setattr(cleaning_module, "add_source_row_id", _broken_add_id)

    with pytest.raises(CleaningError, match="Row count changed"):
        cleaning_module.clean_dataset(classification_df)


def test_compute_cleaning_summary_known_values(classification_df, cleaned):
    summary = compute_cleaning_summary(classification_df, cleaned)

    assert summary["row_count_raw"] == summary["row_count_cleaned"] == 10
    assert summary["transaction_status_counts"] == {
        "valid_sale": 4,
        "cancellation": 2,
        "potential_return": 1,
        "non_standard": 3,
    }
    assert summary["cancellation_exceptions"] == 1  # row C
    assert summary["invoice_format_exceptions"] == 1  # row F
    assert summary["duplicates"]["candidate_row_count"] == 2
    assert summary["duplicates"]["distinct_group_count"] == 1
    assert summary["duplicates"]["largest_group_size"] == 2

    revenue = summary["revenue"]
    assert revenue["gross_sales_revenue"] == pytest.approx(50.0)  # A+H+I+J = 10+10+15+15
    assert revenue["cancellation_value"] == pytest.approx(0.0)  # B(-6) + C(+6)
    assert revenue["potential_return_value"] == pytest.approx(0.0)
    assert revenue["non_standard_value"] == pytest.approx(60.0)  # E(0)+F(50)+G(10)
    assert revenue["net_revenue"] == pytest.approx(50.0)
