"""Exports the minimal set of warehouse tables/views Power BI needs for Import mode
(see dashboards/powerbi/DATA_MODEL.md for the full rationale).

Deliberately NOT all 19 warehouse views: product/country rankings are simple enough
to recreate as DAX measures over the star schema directly (avoiding redundant data and
any risk of double-counting an already-aggregated view against transaction-level
facts). Only the star schema itself, plus the few Phase 5 views whose logic (RFM
scoring, cohort retention, partial-month detection) is genuinely too complex to sanely
re-derive in DAX, are exported.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# name -> fully-qualified source (table or view) in the warehouse schema.
# Order matters only for readability of the export report.
EXPORT_SOURCES: dict[str, str] = {
    "fact_sales": "warehouse.fact_sales",
    "dim_date": "warehouse.dim_date",
    "dim_product": "warehouse.dim_product",
    "dim_customer": "warehouse.dim_customer",
    "dim_country": "warehouse.dim_country",
    "v_customer_rfm": "warehouse.v_customer_rfm",
    "v_customer_cohort_retention": "warehouse.v_customer_cohort_retention",
    "v_monthly_revenue_growth": "warehouse.v_monthly_revenue_growth",
    "v_duplicate_sensitivity": "warehouse.v_duplicate_sensitivity",
}


class PowerBIExportError(Exception):
    """Raised when an export source can't be read or written."""


@dataclass(frozen=True)
class ExportResult:
    name: str
    source: str
    row_count: int
    column_count: int
    path: Path


def export_table(name: str, source: str, engine: Engine, output_dir: Path) -> ExportResult:
    """Export one table/view to CSV via server-side ``COPY ... TO STDOUT``, streaming
    directly to disk rather than materialising the whole result as a DataFrame first
    (fact_sales alone is 541,909 rows x 18 columns — streaming avoids the memory spike
    of building that as Python objects in one go). Raises PowerBIExportError on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.csv"

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur, path.open("w", encoding="utf-8", newline="") as f:
            with cur.copy(
                f"COPY (SELECT * FROM {source}) TO STDOUT WITH (FORMAT csv, HEADER)"  # noqa: S608
            ) as copy:
                for chunk in copy:
                    f.write(bytes(chunk).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any DB/write failure is a fatal export error
        raise PowerBIExportError(f"Failed to export {source}: {exc}") from exc
    finally:
        raw_conn.close()

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        row_count = sum(1 for _ in reader)

    logger.info("Exported %s -> %s (%d rows, %d columns)", source, path, row_count, len(header))

    return ExportResult(
        name=name, source=source, row_count=row_count, column_count=len(header), path=path
    )


def export_all(engine: Engine, output_dir: Path) -> list[ExportResult]:
    """Export every table in EXPORT_SOURCES. Returns one ExportResult per table."""
    return [
        export_table(name, source, engine, output_dir)
        for name, source in EXPORT_SOURCES.items()
    ]


def verify_export(result: ExportResult, engine: Engine) -> bool:
    """Re-count the live source and compare against the exported CSV's row count."""
    with engine.connect() as conn:
        live_count = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {result.source}")  # noqa: S608
        ).scalar_one()
    return live_count == result.row_count
