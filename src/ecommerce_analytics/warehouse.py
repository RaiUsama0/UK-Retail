"""Loads the Phase 3 cleaned dataset into a PostgreSQL star schema.

Pipeline: schema init (idempotent DDL) -> bulk COPY into a staging table -> SQL
upserts into dimensions -> SQL upsert into fact_sales -> reconciliation against the
source dataframe. The whole load (staging through fact) runs in a single database
transaction, so a failure anywhere rolls back everything — never a partially
committed load. Idempotency comes from database constraints (``ON CONFLICT`` upserts
keyed on real primary/unique keys), not an application-level "check if it exists
first" pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from ecommerce_analytics.cleaning import CLEANED_COLUMNS
from ecommerce_analytics.config import DatabaseConfig, load_database_config

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = _REPO_ROOT / "sql" / "schema"
TRANSFORM_DIR = _REPO_ROOT / "sql" / "transformations"

# staging.stg_cleaned_sales' column order mirrors cleaning.CLEANED_COLUMNS exactly (see
# sql/schema/002_staging.sql) — reused directly so the two can never silently drift.
STAGING_COLUMNS = CLEANED_COLUMNS

TRANSACTION_STATUSES = ("valid_sale", "cancellation", "potential_return", "non_standard")


class WarehouseError(Exception):
    """Fatal warehouse failure: connection, schema init, or a load that had to be
    rolled back (constraint violation, bad input, etc.)."""


@dataclass(frozen=True)
class LoadResult:
    staging_rows_loaded: int
    fact_rows_after_load: int


@dataclass(frozen=True)
class ReconciliationCheck:
    name: str
    expected: Any
    actual: Any
    passed: bool


@dataclass(frozen=True)
class ReconciliationResult:
    checks: list[ReconciliationCheck]

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def build_engine(config: DatabaseConfig | None = None) -> Engine:
    """Create and verify a SQLAlchemy engine. Raises WarehouseError if unreachable."""
    cfg = config or load_database_config()
    engine = sa.create_engine(cfg.sqlalchemy_url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except OperationalError as exc:
        raise WarehouseError(
            f"Could not connect to PostgreSQL at {cfg.host}:{cfg.port}/{cfg.name}. "
            f"Is the container running (`docker compose up -d`)? Original error: {exc}"
        ) from exc
    return engine


def _read_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def initialise_schema(engine: Engine) -> None:
    """Idempotently apply every DDL script in sql/schema/, in filename order.

    Safe to run on every pipeline start regardless of whether Postgres's own
    ``docker-entrypoint-initdb.d`` first-boot mechanism already applied them — every
    statement uses ``IF NOT EXISTS`` / ``CREATE OR REPLACE``, so re-application is a
    no-op. Never drops or alters existing objects.
    """
    scripts = sorted(SCHEMA_DIR.glob("*.sql"))
    if not scripts:
        raise WarehouseError(f"No schema scripts found in {SCHEMA_DIR}")

    with engine.begin() as conn:
        for script in scripts:
            logger.info("Applying schema script: %s", script.name)
            conn.execute(sa.text(_read_sql_file(script)))


def _to_copy_buffer(df: pd.DataFrame) -> str:
    ordered = df[STAGING_COLUMNS]
    return ordered.to_csv(index=False, header=False, na_rep="")


def load_warehouse(cleaned_df: pd.DataFrame, engine: Engine) -> LoadResult:
    """Truncate + bulk-load staging, then upsert dimensions and fact_sales — all in a
    single transaction. Raises WarehouseError (with rollback already performed) on any
    failure.
    """
    missing_cols = set(STAGING_COLUMNS) - set(cleaned_df.columns)
    if missing_cols:
        raise WarehouseError(f"Cleaned dataframe is missing expected columns: {missing_cols}")

    csv_payload = _to_copy_buffer(cleaned_df)
    dim_sql = _read_sql_file(TRANSFORM_DIR / "010_load_dimensions.sql")
    fact_sql = _read_sql_file(TRANSFORM_DIR / "020_load_fact.sql")

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            logger.info("Truncating staging table")
            cur.execute("TRUNCATE TABLE staging.stg_cleaned_sales")

            logger.info("Bulk-loading %d rows into staging via COPY", len(cleaned_df))
            copy_sql = (
                "COPY staging.stg_cleaned_sales (" + ", ".join(STAGING_COLUMNS) + ") "
                "FROM STDIN WITH (FORMAT csv, NULL '')"
            )
            with cur.copy(copy_sql) as copy:
                copy.write(csv_payload)

            logger.info("Upserting dimension tables")
            cur.execute(dim_sql)

            logger.info("Upserting fact_sales")
            cur.execute(fact_sql)

            cur.execute("SELECT COUNT(*) FROM warehouse.fact_sales")
            fact_row_count = cur.fetchone()[0]

        raw_conn.commit()
    except Exception as exc:
        raw_conn.rollback()
        raise WarehouseError(f"Warehouse load failed and was rolled back: {exc}") from exc
    finally:
        raw_conn.close()

    logger.info(
        "Load committed: staging=%d rows, fact_sales now has %d rows",
        len(cleaned_df),
        fact_row_count,
    )
    return LoadResult(staging_rows_loaded=len(cleaned_df), fact_rows_after_load=fact_row_count)


def _decimal_sum(quantities: pd.Series, unit_prices: pd.Series) -> Decimal:
    total = Decimal("0")
    for q, p in zip(quantities.to_numpy(), unit_prices.to_numpy(), strict=True):
        total += Decimal(str(q)) * Decimal(str(p))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reconcile(cleaned_df: pd.DataFrame, engine: Engine) -> ReconciliationResult:
    """Compare the warehouse's fact_sales against the source dataframe it was loaded
    from. Every "expected" value is derived from ``cleaned_df`` itself — nothing here
    is a hardcoded universal constant, so this works identically for the real 541,909-
    row dataset and for a small synthetic test fixture.
    """
    is_sale = cleaned_df["transaction_status"] == "valid_sale"
    is_cancel = cleaned_df["transaction_status"] == "cancellation"
    is_return = cleaned_df["transaction_status"] == "potential_return"

    expected_gross = _decimal_sum(
        cleaned_df.loc[is_sale, "quantity"], cleaned_df.loc[is_sale, "unit_price"]
    )
    expected_cancel = _decimal_sum(
        cleaned_df.loc[is_cancel, "quantity"], cleaned_df.loc[is_cancel, "unit_price"]
    )
    expected_return = _decimal_sum(
        cleaned_df.loc[is_return, "quantity"], cleaned_df.loc[is_return, "unit_price"]
    )
    expected_net = expected_gross + expected_cancel

    expected_status_counts = cleaned_df["transaction_status"].value_counts().to_dict()

    with engine.connect() as conn:
        actual_row_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.fact_sales")
        ).scalar_one()
        actual_unique_ids = conn.execute(
            sa.text("SELECT COUNT(DISTINCT source_row_id) FROM warehouse.fact_sales")
        ).scalar_one()
        status_counts = dict(
            conn.execute(
                sa.text(
                    "SELECT transaction_status, COUNT(*) FROM warehouse.fact_sales "
                    "GROUP BY transaction_status"
                )
            ).all()
        )
        actual_missing_customer = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.fact_sales WHERE customer_key IS NULL")
        ).scalar_one()
        actual_duplicate_candidates = conn.execute(
            sa.text("SELECT COUNT(*) FROM warehouse.fact_sales WHERE flag_duplicate_candidate")
        ).scalar_one()
        actual_gross = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(line_revenue), 0) FROM warehouse.fact_sales "
                "WHERE transaction_status = 'valid_sale'"
            )
        ).scalar_one()
        actual_cancel = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(line_revenue), 0) FROM warehouse.fact_sales "
                "WHERE transaction_status = 'cancellation'"
            )
        ).scalar_one()
        actual_return = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(line_revenue), 0) FROM warehouse.fact_sales "
                "WHERE transaction_status = 'potential_return'"
            )
        ).scalar_one()

    actual_gross = Decimal(actual_gross)
    actual_cancel = Decimal(actual_cancel)
    actual_return = Decimal(actual_return)
    actual_net = actual_gross + actual_cancel

    checks: list[ReconciliationCheck] = [
        ReconciliationCheck(
            "fact_row_count", len(cleaned_df), actual_row_count, len(cleaned_df) == actual_row_count
        ),
        ReconciliationCheck(
            "unique_source_row_ids",
            int(cleaned_df["source_row_id"].nunique()),
            actual_unique_ids,
            int(cleaned_df["source_row_id"].nunique()) == actual_unique_ids,
        ),
    ]
    for status in TRANSACTION_STATUSES:
        expected = int(expected_status_counts.get(status, 0))
        actual = int(status_counts.get(status, 0))
        checks.append(
            ReconciliationCheck(f"status_count_{status}", expected, actual, expected == actual)
        )

    expected_missing_customer = int(cleaned_df["flag_missing_customer_id"].sum())
    checks.append(
        ReconciliationCheck(
            "missing_customer_id_count",
            expected_missing_customer,
            actual_missing_customer,
            expected_missing_customer == actual_missing_customer,
        )
    )
    expected_duplicates = int(cleaned_df["flag_duplicate_candidate"].sum())
    checks.append(
        ReconciliationCheck(
            "duplicate_candidate_count",
            expected_duplicates,
            actual_duplicate_candidates,
            expected_duplicates == actual_duplicate_candidates,
        )
    )
    checks.append(
        ReconciliationCheck(
            "gross_sales_revenue",
            str(expected_gross),
            str(actual_gross),
            expected_gross == actual_gross,
        )
    )
    checks.append(
        ReconciliationCheck(
            "cancellation_value",
            str(expected_cancel),
            str(actual_cancel),
            expected_cancel == actual_cancel,
        )
    )
    checks.append(
        ReconciliationCheck(
            "potential_return_value",
            str(expected_return),
            str(actual_return),
            expected_return == actual_return,
        )
    )
    checks.append(
        ReconciliationCheck(
            "net_revenue", str(expected_net), str(actual_net), expected_net == actual_net
        )
    )

    result = ReconciliationResult(checks=checks)
    for check in result.checks:
        if not check.passed:
            logger.warning(
                "Reconciliation MISMATCH [%s]: expected=%s actual=%s",
                check.name,
                check.expected,
                check.actual,
            )
    return result


def render_load_report_markdown(
    load_result: LoadResult, reconciliation: ReconciliationResult
) -> str:
    rows = "\n".join(
        f"| {c.name} | {c.expected} | {c.actual} | {'PASS' if c.passed else 'FAIL'} |"
        for c in reconciliation.checks
    )
    overall = "ALL CHECKS PASSED" if reconciliation.all_passed else "RECONCILIATION FAILED"

    return f"""# Warehouse Load Report

## Load result

- Staging rows loaded: **{load_result.staging_rows_loaded:,}**
- fact_sales row count after load: **{load_result.fact_rows_after_load:,}**

## Reconciliation ({overall})

Every "expected" value below is derived from the source cleaned dataframe at load
time — not a hardcoded constant — and compared against the equivalent aggregate
queried back from PostgreSQL.

| Check | Expected | Actual | Result |
|---|---|---|---|
{rows}
"""


def save_load_report(
    load_result: LoadResult,
    reconciliation: ReconciliationResult,
    json_path: Path,
    markdown_path: Path,
) -> None:
    import json

    payload = {
        "staging_rows_loaded": load_result.staging_rows_loaded,
        "fact_rows_after_load": load_result.fact_rows_after_load,
        "all_checks_passed": reconciliation.all_passed,
        "checks": [
            {"name": c.name, "expected": c.expected, "actual": c.actual, "passed": c.passed}
            for c in reconciliation.checks
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    markdown_text = render_load_report_markdown(load_result, reconciliation)
    markdown_path.write_text(markdown_text, encoding="utf-8")
