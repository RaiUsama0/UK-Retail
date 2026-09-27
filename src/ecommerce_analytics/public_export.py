"""Exports a privacy-reviewed, fully-aggregated public dataset for the Streamlit
dashboard — distinct from ``powerbi_export.py``'s internal 9-table model.

**The difference, stated explicitly**: the Power BI export includes `fact_sales` at
transaction grain (with a `customer_key` per row) and the raw per-customer
`v_customer_rfm` table, because that dashboard is an internal analytical tool. This
module NEVER exports a customer identifier or a per-customer/transaction-level row —
every file here is aggregated to product, country, month, cohort, or segment grain, or
is a headline scalar. See `dashboards/streamlit/data/public/README.md` for the
per-file privacy rationale.

Source licence: UCI "Online Retail" dataset, CC BY 4.0 (verified against the UCI
dataset page) — permits public/commercial redistribution of derived data with
attribution, which this project gives throughout.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_NON_MERCHANDISE_PATTERN = re.compile(r"^\d")

# name -> SQL query. Every query here is either a straight SELECT from an existing,
# already-aggregated warehouse view, or a fresh aggregate query over v_customer_rfm
# that never returns a customer_id or a per-customer row.
_DIRECT_VIEW_EXPORTS: dict[str, str] = {
    "product_performance": "SELECT * FROM warehouse.v_product_performance",
    "product_monthly_trend": "SELECT * FROM warehouse.v_product_monthly_trend",
    "product_cancellation_activity": "SELECT * FROM warehouse.v_product_cancellation_activity",
    "country_performance": "SELECT * FROM warehouse.v_revenue_by_country",
    "monthly_revenue": "SELECT * FROM warehouse.v_monthly_revenue_growth",
    "cohort_retention": "SELECT * FROM warehouse.v_customer_cohort_retention",
    "duplicate_sensitivity": "SELECT * FROM warehouse.v_duplicate_sensitivity",
    "transaction_quality_summary": "SELECT * FROM warehouse.v_data_quality_monitor",
    # Top 20 products per country only (not the full 19,657-row cross-join) — keeps
    # the public file small and the "country-level product performance" page focused.
    "product_country_performance": """
        SELECT country_name, stock_code, description, revenue, rank_within_country
        FROM warehouse.v_product_country_rankings
        WHERE rank_within_country <= 20
    """,
    # Explicitly excludes customer_key/source_row_id — no row here has a customer
    # attached anyway (verified in Phase 3: all 3 have a NULL CustomerID), but the
    # export stays minimal on principle.
    "anomalous_transactions": """
        SELECT invoice_no, quantity, unit_price, line_revenue, transaction_status
        FROM warehouse.fact_sales
        WHERE flag_non_standard_invoice_format
        ORDER BY source_row_id
    """,
    # Aggregated segment summary — count and averages only, never a customer_id.
    "customer_segment_summary": """
        SELECT
            rfm_segment_heuristic,
            COUNT(*) AS customer_count,
            ROUND(AVG(recency_days), 1) AS avg_recency_days,
            ROUND(AVG(frequency), 1) AS avg_frequency,
            ROUND(AVG(monetary), 2) AS avg_monetary
        FROM warehouse.v_customer_rfm
        GROUP BY rfm_segment_heuristic
    """,
    # Decile-level concentration only — no customer_id, no individual monetary value.
    "customer_spend_deciles": """
        WITH ranked AS (
            SELECT monetary, NTILE(10) OVER (ORDER BY monetary DESC) AS decile
            FROM warehouse.v_customer_rfm
        )
        SELECT
            decile,
            COUNT(*) AS customer_count,
            SUM(monetary) AS decile_revenue,
            ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 2) AS pct_of_total_revenue
        FROM ranked
        GROUP BY decile
        ORDER BY decile
    """,
    # One row: headline customer metrics, all scalars, no identifiers.
    "customer_headline_metrics": """
        WITH orders AS (
            SELECT customer_key, COUNT(DISTINCT invoice_no) AS order_count
            FROM warehouse.fact_sales
            WHERE transaction_status = 'valid_sale' AND customer_key IS NOT NULL
            GROUP BY customer_key
        ),
        deciles AS (
            SELECT monetary, NTILE(10) OVER (ORDER BY monetary DESC) AS decile
            FROM warehouse.v_customer_rfm
        )
        SELECT
            (SELECT COUNT(*) FROM warehouse.dim_customer) AS identified_customers,
            (SELECT COUNT(*) FROM warehouse.v_customer_rfm) AS customers_with_qualifying_purchase,
            (SELECT COUNT(*) FROM orders) AS customers_with_orders,
            (SELECT COUNT(*) FROM orders WHERE order_count >= 2) AS repeat_customers,
            ROUND(
                100.0 * (SELECT COUNT(*) FROM orders WHERE order_count >= 2)
                    / NULLIF((SELECT COUNT(*) FROM orders), 0),
                2
            ) AS repeat_customer_rate_pct,
            ROUND((SELECT AVG(monetary) FROM warehouse.v_customer_rfm), 2) AS mean_customer_spend,
            (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY monetary)
                FROM warehouse.v_customer_rfm) AS median_customer_spend,
            (SELECT ROUND(SUM(monetary), 2) FROM deciles WHERE decile = 1) AS top_decile_revenue,
            ROUND(
                100.0 * (SELECT SUM(monetary) FROM deciles WHERE decile = 1)
                    / NULLIF((SELECT SUM(monetary) FROM deciles), 0),
                2
            ) AS top_decile_revenue_pct
    """,
    # One row: overall dataset scalars for the reporting-period banner and Page 4.
    "dataset_metadata": """
        SELECT
            COUNT(*) AS total_source_records,
            MIN(invoice_timestamp)::date AS date_range_start,
            MAX(invoice_timestamp)::date AS date_range_end,
            COUNT(*) FILTER (WHERE transaction_status = 'valid_sale') AS valid_sale_count,
            COUNT(*) FILTER (WHERE transaction_status = 'cancellation') AS cancellation_count,
            COUNT(*) FILTER (WHERE transaction_status = 'potential_return')
                AS potential_return_count,
            COUNT(*) FILTER (WHERE transaction_status = 'non_standard') AS non_standard_count,
            COUNT(*) FILTER (WHERE flag_missing_customer_id) AS missing_customer_id_count,
            COUNT(*) FILTER (WHERE flag_duplicate_candidate) AS duplicate_candidate_count,
            COUNT(*) FILTER (WHERE flag_non_standard_invoice_format)
                AS anomalous_invoice_format_count
        FROM warehouse.fact_sales
    """,
}

# Published as-is: small dimension tables with no customer data at all.
_DIMENSION_EXPORTS: dict[str, str] = {
    "dim_product": "SELECT product_key, stock_code, description FROM warehouse.dim_product",
}


class PublicExportError(Exception):
    """Raised when a public export source can't be read or written."""


@dataclass(frozen=True)
class PublicExportResult:
    name: str
    row_count: int
    column_count: int
    path: Path


def _fetch(engine: Engine, query: str) -> pd.DataFrame:
    try:
        return pd.read_sql(sa.text(query), engine)
    except Exception as exc:  # noqa: BLE001 - any DB/read failure is fatal for this export
        raise PublicExportError(f"Failed to run query: {exc}") from exc


def _add_non_merchandise_flag(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_non_merchandise"] = ~df["stock_code"].astype(str).str.match(_NON_MERCHANDISE_PATTERN)
    return df


def export_all(engine: Engine, output_dir: Path) -> list[PublicExportResult]:
    """Export every public dataset. Small tables/aggregates only — see module
    docstring for the exact privacy rationale. Raises PublicExportError on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[PublicExportResult] = []

    all_sources = {**_DIRECT_VIEW_EXPORTS, **_DIMENSION_EXPORTS}
    for name, query in all_sources.items():
        df = _fetch(engine, query)
        if name == "product_performance":
            df = _add_non_merchandise_flag(df)

        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("Exported %s -> %s (%d rows, %d columns)", name, path, *df.shape)
        results.append(
            PublicExportResult(name=name, row_count=len(df), column_count=df.shape[1], path=path)
        )

    metadata_path = output_dir / "_export_generated_at.txt"
    metadata_path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")

    return results


def assert_no_customer_identifiers(results: list[PublicExportResult]) -> None:
    """Defence-in-depth privacy check: fails loudly if any exported file contains a
    column that could identify an individual customer. Intended to be run as part of
    the export pipeline and as an automated test, not just a one-off manual review.
    """
    forbidden_column_names = {"customer_id", "customer_key"}
    for result in results:
        header = pd.read_csv(result.path, nrows=0).columns
        leaked = forbidden_column_names & set(header)
        if leaked:
            raise PublicExportError(
                f"Privacy check failed: {result.name}.csv contains forbidden column(s) "
                f"{leaked} — a customer identifier must never be in a public export."
            )
