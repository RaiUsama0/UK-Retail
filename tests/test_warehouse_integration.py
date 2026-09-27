"""Integration tests against a real PostgreSQL instance (see conftest.py's `db_engine`
/ `clean_warehouse` fixtures — a dedicated `<database>_test` database, never the real
development database). Skipped automatically if Postgres isn't reachable.
"""

from decimal import Decimal

import pandas as pd
import pytest
import sqlalchemy as sa

from ecommerce_analytics.cleaning import clean_dataset
from ecommerce_analytics.warehouse import (
    WarehouseError,
    initialise_schema,
    load_warehouse,
    reconcile,
)


@pytest.fixture
def cleaned_fixture(sample_df) -> pd.DataFrame:
    return clean_dataset(sample_df)


def test_initialise_schema_creates_expected_objects(clean_warehouse):
    with clean_warehouse.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema IN ('staging', 'warehouse')"
                )
            ).all()
        }
    expected = {
        "stg_cleaned_sales",
        "dim_date",
        "dim_country",
        "dim_customer",
        "dim_product",
        "fact_sales",
    }
    assert expected <= tables


def test_initialise_schema_is_idempotent(clean_warehouse):
    initialise_schema(clean_warehouse)  # clean_warehouse fixture already ran it once
    initialise_schema(clean_warehouse)  # must not raise on a second application


def test_load_warehouse_preserves_row_count(clean_warehouse, cleaned_fixture):
    result = load_warehouse(cleaned_fixture, clean_warehouse)
    assert result.staging_rows_loaded == len(cleaned_fixture)
    assert result.fact_rows_after_load == len(cleaned_fixture)


def test_load_warehouse_preserves_duplicate_candidates(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.fact_sales WHERE flag_duplicate_candidate")
        ).scalar_one()
    expected = int(cleaned_fixture["flag_duplicate_candidate"].sum())
    assert count == expected == 2  # rows 0 and 7 in sample_df


def test_load_warehouse_nullable_customer_key_for_missing_customer_id(
    clean_warehouse, cleaned_fixture
):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.connect() as conn:
        null_customer_key_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.fact_sales WHERE customer_key IS NULL")
        ).scalar_one()
    expected = int(cleaned_fixture["flag_missing_customer_id"].sum())
    assert null_customer_key_count == expected


def test_load_warehouse_does_not_invent_customer_rows(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.connect() as conn:
        dim_customer_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.dim_customer")
        ).scalar_one()
    expected = int(cleaned_fixture["customer_id"].dropna().nunique())
    assert dim_customer_count == expected


def test_load_warehouse_monetary_precision(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT source_row_id, line_revenue FROM warehouse.fact_sales "
                "ORDER BY source_row_id"
            )
        ).all()
    for source_row_id, line_revenue in rows:
        raw_value = cleaned_fixture.loc[source_row_id, "line_revenue"]
        expected = Decimal(str(raw_value)).quantize(Decimal("0.01"))
        assert Decimal(line_revenue) == expected


def test_load_warehouse_transaction_status_preserved(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.connect() as conn:
        db_counts = dict(
            conn.execute(
                sa.text(
                    "SELECT transaction_status, COUNT(*) FROM warehouse.fact_sales "
                    "GROUP BY transaction_status"
                )
            ).all()
        )
    expected_counts = cleaned_fixture["transaction_status"].value_counts().to_dict()
    for status, expected in expected_counts.items():
        assert db_counts.get(status, 0) == expected


def test_load_warehouse_is_idempotent(clean_warehouse, cleaned_fixture):
    first = load_warehouse(cleaned_fixture, clean_warehouse)
    second = load_warehouse(cleaned_fixture, clean_warehouse)
    assert first.fact_rows_after_load == second.fact_rows_after_load == len(cleaned_fixture)

    with clean_warehouse.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM warehouse.fact_sales")).scalar_one()
        distinct_ids = conn.execute(
            sa.text("SELECT COUNT(DISTINCT source_row_id) FROM warehouse.fact_sales")
        ).scalar_one()
    assert count == distinct_ids == len(cleaned_fixture)


def test_load_warehouse_rolls_back_on_failure(clean_warehouse, cleaned_fixture):
    with clean_warehouse.connect() as conn:
        before = conn.execute(sa.text("SELECT COUNT(*) FROM warehouse.fact_sales")).scalar_one()

    broken = cleaned_fixture.copy()
    broken["transaction_status"] = broken["transaction_status"].astype(object)
    broken.loc[broken.index[0], "transaction_status"] = None  # violates staging NOT NULL

    with pytest.raises(WarehouseError):
        load_warehouse(broken, clean_warehouse)

    with clean_warehouse.connect() as conn:
        after = conn.execute(sa.text("SELECT COUNT(*) FROM warehouse.fact_sales")).scalar_one()
    assert after == before  # nothing was partially committed


def test_reconcile_passes_after_successful_load(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    result = reconcile(cleaned_fixture, clean_warehouse)
    assert result.all_passed
    assert all(c.passed for c in result.checks)


def test_reconcile_detects_a_real_mismatch(clean_warehouse, cleaned_fixture):
    load_warehouse(cleaned_fixture, clean_warehouse)
    with clean_warehouse.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE warehouse.fact_sales SET line_revenue = line_revenue + 1000 "
                "WHERE source_row_id = 0"
            )
        )
    result = reconcile(cleaned_fixture, clean_warehouse)
    assert not result.all_passed
    revenue_checks = {c.name: c for c in result.checks}
    assert not revenue_checks["gross_sales_revenue"].passed
