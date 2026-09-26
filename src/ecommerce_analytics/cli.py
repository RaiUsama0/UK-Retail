"""CLI entry point: run ingestion + profiling + validation and print a summary.

Usage (from the repository root, with the package installed):

    ingest-data
    python -m ecommerce_analytics.cli
    python -m ecommerce_analytics.cli --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from ecommerce_analytics.config import load_pipeline_config
from ecommerce_analytics.ingestion import IngestionError, ingest_raw_file, load_dataset
from ecommerce_analytics.profiling import compute_profile, save_reports
from ecommerce_analytics.validation import SchemaValidationError, derive_warnings, validate_schema

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest-data",
        description="Ingest the Online Retail dataset, validate it, and generate profiling reports.",  # noqa: E501
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing raw copy even if its checksum differs from the source.",
    )
    args = parser.parse_args(argv)

    log_file = load_pipeline_config().reports_dir / "ingestion.log"
    configure_logging(log_file=log_file)

    try:
        result = run_ingestion_pipeline(force=args.force)
    except IngestionError as exc:
        logger.error("Ingestion failed: %s", exc)
        return 1
    except SchemaValidationError as exc:
        logger.error("Schema validation failed: %s", exc)
        return 1

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
