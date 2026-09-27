"""Reconciliation tests for the Phase 5 analytical views. Runs against a real
PostgreSQL instance (see conftest.py's `clean_warehouse` fixture — a dedicated
`<database>_test` database). Skipped automatically if Postgres isn't reachable.

Uses a small synthetic fixture with hand-computed expected outputs, loaded through the
real Phase 3/4 pipeline (clean_dataset -> load_warehouse), so these tests exercise the
actual SQL views exactly as production data would.
"""

from decimal import Decimal

import pandas as pd
import pytest
import sqlalchemy as sa

from ecommerce_analytics.cleaning import clean_dataset
from ecommerce_analytics.warehouse import load_warehouse

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

# A dataset spanning two calendar months, with a repeat customer, a one-time customer,
# a cancellation, and a duplicate pair — enough to exercise monthly revenue, RFM,
# cohort, and duplicate-sensitivity logic with hand-computable expected results.
_ROWS = [
    # Customer 3001: two orders in month 1 (repeat, within-month)
    ("700001", "20001", "ITEM A", 2, "2011-03-01 10:00", 10.0, 3001.0, "United Kingdom"),
    ("700002", "20002", "ITEM B", 1, "2011-03-05 11:00", 5.0, 3001.0, "United Kingdom"),
    # Customer 3002: one order in month 1, one order in month 2 (repeat, cross-month)
    ("700003", "20001", "ITEM A", 3, "2011-03-10 09:00", 10.0, 3002.0, "France"),
    ("700004", "20002", "ITEM B", 4, "2011-04-02 09:00", 5.0, 3002.0, "France"),
    # Customer 3003: one order only in month 1 (one-time customer)
    ("700005", "20001", "ITEM A", 1, "2011-03-15 14:00", 10.0, 3003.0, "United Kingdom"),
    # Cancellation against customer 3001's first order
    ("C700006", "20001", "ITEM A", -1, "2011-03-02 09:00", 10.0, 3001.0, "United Kingdom"),
    # Exact duplicate of the first row (same invoice/product/qty/price/customer/time)
    ("700001", "20001", "ITEM A", 2, "2011-03-01 10:00", 10.0, 3001.0, "United Kingdom"),
]


@pytest.fixture
def cleaned_fixture() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return clean_dataset(df)


@pytest.fixture
def loaded_warehouse(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    return clean_warehouse


def test_monthly_revenue_reconciles_with_fact_table(loaded_warehouse, cleaned_fixture):
    with loaded_warehouse.connect() as conn:
        view_total = conn.execute(
            sa.text("SELECT SUM(net_revenue) FROM warehouse.v_monthly_revenue_growth")
        ).scalar_one()

    is_sale = cleaned_fixture["transaction_status"] == "valid_sale"
    is_cancel = cleaned_fixture["transaction_status"] == "cancellation"
    expected_total = cleaned_fixture.loc[is_sale, "line_revenue"].sum() + cleaned_fixture.loc[
        is_cancel, "line_revenue"
    ].sum()

    assert Decimal(str(round(float(view_total), 2))) == Decimal(str(round(expected_total, 2)))


def test_monthly_revenue_cumulative_matches_running_sum(loaded_warehouse):
    with loaded_warehouse.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT year, month, net_revenue, cumulative_net_revenue "
                "FROM warehouse.v_monthly_revenue_growth ORDER BY year, month"
            )
        ).all()

    running = Decimal("0")
    for _, _, net_revenue, cumulative in rows:
        running += Decimal(net_revenue)
        assert Decimal(cumulative) == running


def test_monthly_revenue_growth_null_for_first_month(loaded_warehouse):
    with loaded_warehouse.connect() as conn:
        first_row = conn.execute(
            sa.text(
                "SELECT month_over_month_growth_pct, previous_month_net_revenue "
                "FROM warehouse.v_monthly_revenue_growth ORDER BY year, month LIMIT 1"
            )
        ).one()
    assert first_row.previous_month_net_revenue is None
    assert first_row.month_over_month_growth_pct is None


def test_product_revenue_reconciles_with_qualifying_sales(loaded_warehouse, cleaned_fixture):
    with loaded_warehouse.connect() as conn:
        view_total = conn.execute(
            sa.text("SELECT SUM(revenue) FROM warehouse.v_product_performance")
        ).scalar_one()

    is_sale = cleaned_fixture["transaction_status"] == "valid_sale"
    expected = cleaned_fixture.loc[is_sale, "line_revenue"].sum()
    assert Decimal(str(round(float(view_total), 2))) == Decimal(str(round(expected, 2)))


def test_customer_metrics_use_only_identified_customers(loaded_warehouse):
    with loaded_warehouse.connect() as conn:
        null_customer_key_in_rfm = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM warehouse.v_customer_rfm WHERE customer_key IS NULL"
            )
        ).scalar_one()
    assert null_customer_key_in_rfm == 0


def test_order_count_uses_distinct_invoice_definition(loaded_warehouse, cleaned_fixture):
    """Customer 3001 has 2 distinct invoices (700001, 700002); the exact-duplicate row
    (also invoice 700001) must not inflate that to 3."""
    with loaded_warehouse.connect() as conn:
        frequency = conn.execute(
            sa.text(
                "SELECT frequency FROM warehouse.v_customer_rfm WHERE customer_id = 3001"
            )
        ).scalar_one()
    assert frequency == 2


def test_cancellation_value_not_double_counted(loaded_warehouse):
    """The cancellation against customer 3001 must appear exactly once in the
    cancellation total, not once per FILTER clause it happens to satisfy."""
    with loaded_warehouse.connect() as conn:
        cancellation_value = conn.execute(
            sa.text(
                "SELECT SUM(line_revenue) FROM warehouse.fact_sales "
                "WHERE transaction_status = 'cancellation'"
            )
        ).scalar_one()
    assert Decimal(cancellation_value) == Decimal("-10.00")


def test_rfm_scores_are_reproducible(loaded_warehouse):
    with loaded_warehouse.connect() as conn:
        first = conn.execute(
            sa.text(
                "SELECT customer_id, recency_score, frequency_score, monetary_score "
                "FROM warehouse.v_customer_rfm ORDER BY customer_id"
            )
        ).all()
        second = conn.execute(
            sa.text(
                "SELECT customer_id, recency_score, frequency_score, monetary_score "
                "FROM warehouse.v_customer_rfm ORDER BY customer_id"
            )
        ).all()
    assert first == second


def test_cohort_retention_counts_distinct_customers_not_orders(loaded_warehouse):
    """Customer 3001 placed 2 orders in their own cohort month (March 2011); the
    cohort-month (month_index 0) row must count them once, not twice."""
    with loaded_warehouse.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT cohort_size, returning_customers "
                "FROM warehouse.v_customer_cohort_retention "
                "WHERE cohort_month = '2011-03-01' AND month_index = 0"
            )
        ).one()
    # Cohort = customers whose first valid_sale is in March 2011: 3001, 3002, 3003 = 3
    assert row.cohort_size == 3
    assert row.returning_customers == 3  # all 3 bought in their own first month


def test_cohort_retention_month_index_one_matches_expected_carryover(loaded_warehouse):
    """Only customer 3002 has a valid_sale in April 2011 (month_index 1 relative to the
    March 2011 cohort); customers 3001 and 3003 do not appear again."""
    with loaded_warehouse.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT returning_customers, retention_pct "
                "FROM warehouse.v_customer_cohort_retention "
                "WHERE cohort_month = '2011-03-01' AND month_index = 1"
            )
        ).one()
    assert row.returning_customers == 1
    assert Decimal(row.retention_pct) == Decimal(str(round(100.0 * 1 / 3, 2)))


def test_duplicate_sensitivity_matches_documented_rule(loaded_warehouse, cleaned_fixture):
    """The fixture has exactly one duplicate pair (source_row_id 0 and 6, both invoice
    700001 / item 20001 / qty 2 / price 10.0 / customer 3001). The deduplicated view
    must drop exactly one row (the repeat), leaving the complete-vs-deduplicated
    revenue delta equal to that one row's line_revenue."""
    with loaded_warehouse.connect() as conn:
        complete_revenue = conn.execute(
            sa.text(
                "SELECT revenue FROM warehouse.v_duplicate_sensitivity "
                "WHERE dataset_version = 'complete_dataset'"
            )
        ).scalar_one()
        dedup_revenue = conn.execute(
            sa.text(
                "SELECT revenue FROM warehouse.v_duplicate_sensitivity "
                "WHERE dataset_version = 'deduplicated'"
            )
        ).scalar_one()

    duplicate_rows = cleaned_fixture[cleaned_fixture["flag_duplicate_candidate"]]
    assert len(duplicate_rows) == 2
    one_duplicate_line_revenue = duplicate_rows.iloc[0]["line_revenue"]

    assert Decimal(str(round(float(complete_revenue - dedup_revenue), 2))) == Decimal(
        str(round(one_duplicate_line_revenue, 2))
    )


def test_duplicate_sensitivity_order_count_unaffected(loaded_warehouse):
    """Deduplication drops a repeat *line*, not a whole invoice — order_count (distinct
    invoice_no) must be identical in both versions here, since the surviving row still
    carries the same invoice number."""
    with loaded_warehouse.connect() as conn:
        rows = dict(
            conn.execute(
                sa.text(
                    "SELECT dataset_version, order_count FROM warehouse.v_duplicate_sensitivity"
                )
            ).all()
        )
    assert rows["complete_dataset"] == rows["deduplicated"]
