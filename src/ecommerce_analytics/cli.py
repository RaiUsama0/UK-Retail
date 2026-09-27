"""CLI entry point: ingestion+profiling, cleaning+classification, and warehouse-loading
workflows.

Usage (from the repository root, with the package installed):

    ingest-data                  # ingest + profile (default)
    ingest-data ingest --force   # same, overwriting a drifted raw copy
    ingest-data clean            # clean, classify, validate, and save processed output
    ingest-data load-warehouse   # load the cleaned dataset into PostgreSQL
    python -m ecommerce_analytics.cli clean
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ecommerce_analytics.cleaning import (
    CleaningError,
    clean_dataset,
    compute_cleaning_summary,
    save_cleaned_dataset,
    save_cleaning_reports,
)
from ecommerce_analytics.config import REPO_ROOT, load_pipeline_config
from ecommerce_analytics.ingestion import IngestionError, ingest_raw_file, load_dataset
from ecommerce_analytics.powerbi_export import (
    ExportResult,
    PowerBIExportError,
    export_all,
    verify_export,
)
from ecommerce_analytics.profiling import compute_profile, save_reports
from ecommerce_analytics.validation import (
    CleaningValidationError,
    SchemaValidationError,
    derive_cleaning_warnings,
    derive_warnings,
    validate_cleaned_dataset,
    validate_schema,
)
from ecommerce_analytics.warehouse import (
    ReconciliationResult,
    WarehouseError,
    build_engine,
    initialise_schema,
    load_warehouse,
    reconcile,
    save_load_report,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    row_count: int
    column_count: int
    was_copied: bool
    raw_path: Path
    sha256: str
    duplicate_rows: int
    warnings: list
    json_report_path: Path
    markdown_report_path: Path


@dataclass(frozen=True)
class CleaningResult:
    row_count: int
    transaction_status_counts: dict
    duplicate_candidate_count: int
    net_revenue: float
    processed_path: Path
    json_report_path: Path
    markdown_report_path: Path
    warnings: list


@dataclass(frozen=True)
class WarehouseLoadCliResult:
    staging_rows_loaded: int
    fact_rows_after_load: int
    reconciliation: ReconciliationResult
    json_report_path: Path
    markdown_report_path: Path


@dataclass(frozen=True)
class PowerBIExportCliResult:
    exports: list[ExportResult]
    all_verified: bool


def configure_logging(log_file: Path | None = None, level: int = logging.INFO) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def run_ingestion_pipeline(force: bool = False) -> PipelineResult:
    """Run ingestion, validation, and profiling once. Returns a summary result.

    Raises :class:`~ecommerce_analytics.ingestion.IngestionError` or
    :class:`~ecommerce_analytics.validation.SchemaValidationError` on fatal failures.
    """
    cfg = load_pipeline_config()

    logger.info("Starting ingestion from %s", cfg.source_xlsx_path)
    ingested = ingest_raw_file(config=cfg, force=force)

    df = load_dataset(ingested)

    logger.info("Running structural schema validation")
    validate_schema(df)
    logger.info("Schema validation passed")

    logger.info("Computing data profile")
    profile = compute_profile(df)
    warnings = derive_warnings(profile)

    json_path = cfg.reports_dir / "data_profile.json"
    markdown_path = cfg.reports_dir / "data_profile.md"
    save_reports(profile, json_path, markdown_path)
    logger.info("Reports written to %s and %s", json_path, markdown_path)

    for w in warnings:
        log_fn = logger.warning if w.severity == "warning" else logger.info
        log_fn("[%s] %s", w.rule, w.message)

    return PipelineResult(
        row_count=profile["row_count"],
        column_count=profile["column_count"],
        was_copied=ingested.was_copied,
        raw_path=ingested.raw_path,
        sha256=ingested.sha256,
        duplicate_rows=profile["duplicate_rows"],
        warnings=warnings,
        json_report_path=json_path,
        markdown_report_path=markdown_path,
    )


def run_cleaning_pipeline(force: bool = False) -> CleaningResult:
    """Ingest (checksum-verify only, no redundant copy), load the raw dataset exactly
    once, then clean, classify, validate, and persist the analysis-ready output.

    Raises :class:`~ecommerce_analytics.ingestion.IngestionError`,
    :class:`~ecommerce_analytics.validation.SchemaValidationError`, or
    :class:`~ecommerce_analytics.validation.CleaningValidationError` on fatal failures.
    """
    cfg = load_pipeline_config()

    logger.info("Verifying raw dataset before cleaning")
    ingested = ingest_raw_file(config=cfg, force=force)

    raw_df = load_dataset(ingested)  # the one and only Excel parse for this run

    logger.info("Running structural schema validation on raw data")
    validate_schema(raw_df)

    logger.info("Cleaning and classifying %d rows", len(raw_df))
    cleaned_df = clean_dataset(raw_df)

    logger.info("Validating cleaned dataset invariants")
    validate_cleaned_dataset(raw_df, cleaned_df)
    logger.info("Cleaned dataset validation passed")

    summary = compute_cleaning_summary(raw_df, cleaned_df)
    warnings = derive_cleaning_warnings(summary)

    processed_path = cfg.processed_data_dir / "online_retail_cleaned.parquet"
    save_cleaned_dataset(cleaned_df, processed_path)

    json_path = cfg.reports_dir / "cleaning_summary.json"
    markdown_path = cfg.reports_dir / "cleaning_summary.md"
    save_cleaning_reports(summary, json_path, markdown_path)
    logger.info("Cleaning reports written to %s and %s", json_path, markdown_path)

    for w in warnings:
        log_fn = logger.warning if w.severity == "warning" else logger.info
        log_fn("[%s] %s", w.rule, w.message)

    return CleaningResult(
        row_count=summary["row_count_cleaned"],
        transaction_status_counts=summary["transaction_status_counts"],
        duplicate_candidate_count=summary["duplicates"]["candidate_row_count"],
        net_revenue=summary["revenue"]["net_revenue"],
        processed_path=processed_path,
        json_report_path=json_path,
        markdown_report_path=markdown_path,
        warnings=warnings,
    )


def run_warehouse_load_pipeline() -> WarehouseLoadCliResult:
    """Load the Phase 3 processed Parquet dataset into PostgreSQL.

    Reads the already-validated cleaned dataset (does not re-run ingestion/cleaning),
    connects to PostgreSQL, idempotently applies the schema, loads staging ->
    dimensions -> fact_sales in a single transaction, then reconciles the warehouse
    against the source dataframe.

    Raises :class:`~ecommerce_analytics.warehouse.WarehouseError` on connection
    failure, missing processed dataset, or a load that had to be rolled back.
    """
    cfg = load_pipeline_config()
    processed_path = cfg.processed_data_dir / "online_retail_cleaned.parquet"

    if not processed_path.exists():
        raise WarehouseError(
            f"Processed dataset not found at {processed_path}. Run `ingest-data clean` first."
        )

    logger.info("Reading processed dataset from %s", processed_path)
    cleaned_df = pd.read_parquet(processed_path)

    logger.info("Connecting to PostgreSQL")
    engine = build_engine()

    logger.info("Initialising/verifying warehouse schema")
    initialise_schema(engine)

    logger.info("Loading %d rows into the warehouse", len(cleaned_df))
    load_result = load_warehouse(cleaned_df, engine)

    logger.info("Reconciling warehouse against source dataset")
    reconciliation = reconcile(cleaned_df, engine)
    for check in reconciliation.checks:
        if not check.passed:
            logger.warning(
                "RECONCILIATION MISMATCH [%s]: expected=%s actual=%s",
                check.name,
                check.expected,
                check.actual,
            )

    json_path = cfg.reports_dir / "warehouse_load_report.json"
    markdown_path = cfg.reports_dir / "warehouse_load_report.md"
    save_load_report(load_result, reconciliation, json_path, markdown_path)
    logger.info("Warehouse load reports written to %s and %s", json_path, markdown_path)

    return WarehouseLoadCliResult(
        staging_rows_loaded=load_result.staging_rows_loaded,
        fact_rows_after_load=load_result.fact_rows_after_load,
        reconciliation=reconciliation,
        json_report_path=json_path,
        markdown_report_path=markdown_path,
    )


def run_powerbi_export_pipeline() -> PowerBIExportCliResult:
    """Export the minimal set of warehouse tables/views Power BI Import mode needs
    (see dashboards/powerbi/DATA_MODEL.md) to CSV, then re-count each source live to
    verify the export matches exactly.

    Raises :class:`~ecommerce_analytics.warehouse.WarehouseError` on connection
    failure, or :class:`~ecommerce_analytics.powerbi_export.PowerBIExportError` if a
    source can't be read/written.
    """
    logger.info("Connecting to PostgreSQL")
    engine = build_engine()

    output_dir = REPO_ROOT / "dashboards" / "powerbi" / "data"
    logger.info("Exporting Power BI import tables to %s", output_dir)
    exports = export_all(engine, output_dir)

    all_verified = True
    for result in exports:
        verified = verify_export(result, engine)
        all_verified = all_verified and verified
        logger.info(
            "%s: %d rows exported, live count matches: %s", result.name, result.row_count, verified
        )
        if not verified:
            logger.warning("%s: exported row count does not match the live source!", result.name)

    return PowerBIExportCliResult(exports=exports, all_verified=all_verified)


def _print_ingestion_summary(result: PipelineResult) -> None:
    warning_count = sum(1 for w in result.warnings if w.severity == "warning")
    info_count = sum(1 for w in result.warnings if w.severity == "info")

    print()
    print("=== Ingestion summary ===")
    print(f"Raw file:          {result.raw_path}")
    print(f"SHA-256:           {result.sha256}")
    print(f"Copied this run:   {result.was_copied}")
    print(f"Rows x Columns:    {result.row_count:,} x {result.column_count}")
    print(f"Duplicate rows:    {result.duplicate_rows:,}")
    print(f"Data quality flags: {warning_count} warning(s), {info_count} info notice(s)")
    print(f"JSON report:       {result.json_report_path}")
    print(f"Markdown report:   {result.markdown_report_path}")
    print()


def _print_cleaning_summary(result: CleaningResult) -> None:
    warning_count = sum(1 for w in result.warnings if w.severity == "warning")
    info_count = sum(1 for w in result.warnings if w.severity == "info")

    print()
    print("=== Cleaning summary ===")
    print(f"Rows cleaned:      {result.row_count:,}")
    for status, count in result.transaction_status_counts.items():
        print(f"  {status:<18} {count:,}")
    print(f"Duplicate candidates: {result.duplicate_candidate_count:,}")
    print(f"Net revenue:       £{result.net_revenue:,.2f}")
    print(f"Data quality flags: {warning_count} warning(s), {info_count} info notice(s)")
    print(f"Processed dataset: {result.processed_path}")
    print(f"JSON report:       {result.json_report_path}")
    print(f"Markdown report:   {result.markdown_report_path}")
    print()


def _print_warehouse_load_summary(result: WarehouseLoadCliResult) -> None:
    print()
    print("=== Warehouse load summary ===")
    print(f"Staging rows loaded:     {result.staging_rows_loaded:,}")
    print(f"fact_sales row count:    {result.fact_rows_after_load:,}")
    print("Reconciliation checks:")
    for check in result.reconciliation.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"  [{status}] {check.name}: expected={check.expected} actual={check.actual}")
    print(f"All checks passed:       {result.reconciliation.all_passed}")
    print(f"JSON report:             {result.json_report_path}")
    print(f"Markdown report:         {result.markdown_report_path}")
    print()


def _print_powerbi_export_summary(result: PowerBIExportCliResult) -> None:
    print()
    print("=== Power BI export summary ===")
    for export in result.exports:
        print(f"  {export.name:<30} {export.row_count:>8,} rows  -> {export.path}")
    print(f"All exports verified against live source: {result.all_verified}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest-data",
        description="Ingest, validate, clean, and profile the Online Retail dataset.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="ingest",
        choices=["ingest", "clean", "load-warehouse", "export-powerbi"],
        help="Workflow to run (default: ingest).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing raw copy even if its checksum differs from the source.",
    )

    args = parser.parse_args(argv)
    command = args.command
    force = args.force

    log_file_names = {
        "ingest": "ingestion.log",
        "clean": "cleaning.log",
        "load-warehouse": "warehouse_load.log",
        "export-powerbi": "powerbi_export.log",
    }
    log_file = load_pipeline_config().reports_dir / log_file_names[command]
    configure_logging(log_file=log_file)

    try:
        if command == "ingest":
            _print_ingestion_summary(run_ingestion_pipeline(force=force))
        elif command == "clean":
            _print_cleaning_summary(run_cleaning_pipeline(force=force))
        elif command == "load-warehouse":
            result = run_warehouse_load_pipeline()
            _print_warehouse_load_summary(result)
            if not result.reconciliation.all_passed:
                logger.error("Warehouse load completed but reconciliation found mismatches.")
                return 1
        elif command == "export-powerbi":
            result = run_powerbi_export_pipeline()
            _print_powerbi_export_summary(result)
            if not result.all_verified:
                logger.error("Power BI export completed but a row-count mismatch was found.")
                return 1
        else:
            parser.error(f"Unknown command: {command}")
    except IngestionError as exc:
        logger.error("Ingestion failed: %s", exc)
        return 1
    except SchemaValidationError as exc:
        logger.error("Schema validation failed: %s", exc)
        return 1
    except (CleaningError, CleaningValidationError) as exc:
        logger.error("Cleaning failed: %s", exc)
        return 1
    except WarehouseError as exc:
        logger.error("Warehouse load failed: %s", exc)
        return 1
    except PowerBIExportError as exc:
        logger.error("Power BI export failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
