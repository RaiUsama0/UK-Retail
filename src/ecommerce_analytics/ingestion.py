"""File-level ingestion: preserves an immutable, checksum-verified raw copy of the
source Excel file in ``data/raw/``, without loading or mutating the dataset itself.

Deliberately does not perform any cleaning or business-rule interpretation — see
``validation.py`` (structural + business-rule checks) and Phase 3's ``cleaning.py``.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ecommerce_analytics.config import PipelineConfig, load_pipeline_config
from ecommerce_analytics.schema import EXPECTED_COLUMNS, SHEET_NAME

logger = logging.getLogger(__name__)

CHECKSUM_SUFFIX = ".sha256"


class IngestionError(Exception):
    """Fatal ingestion failure: missing file, corrupt file, or missing required columns."""


@dataclass(frozen=True)
class IngestedFile:
    source_path: Path
    raw_path: Path
    sha256: str
    was_copied: bool


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_sidecar(raw_path: Path) -> Path:
    return raw_path.with_name(raw_path.name + CHECKSUM_SUFFIX)


def _read_header_columns(path: Path) -> list[str]:
    """Read only the header row — fast, and fails loudly on a corrupt/unreadable file."""
    try:
        header_df = pd.read_excel(path, sheet_name=SHEET_NAME, nrows=0)
    except FileNotFoundError as exc:
        raise IngestionError(f"Source file not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001 - any parse failure means a corrupt/invalid file
        raise IngestionError(
            f"Source file could not be read as a valid Excel workbook with sheet "
            f"'{SHEET_NAME}': {path} ({type(exc).__name__}: {exc})"
        ) from exc
    return list(header_df.columns)


def _validate_required_columns(columns: list[str]) -> None:
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    if missing:
        raise IngestionError(
            f"Source file is missing required column(s): {missing}. "
            f"Expected columns: {EXPECTED_COLUMNS}. Found: {columns}."
        )


def ingest_raw_file(
    source_path: Path | None = None,
    raw_dir: Path | None = None,
    force: bool = False,
    config: PipelineConfig | None = None,
) -> IngestedFile:
    """Preserve an immutable, checksum-verified copy of ``source_path`` in ``raw_dir``.

    - Raises :class:`IngestionError` if the source file is missing, corrupt, or is
      missing a required column.
    - If a raw copy already exists and its checksum matches the source, no copy is
      made (the file is verified in place).
    - If a raw copy already exists with a *different* checksum, the copy is refused
      unless ``force=True`` is passed, to avoid silently overwriting a previously
      ingested (and possibly downstream-consumed) raw file.
    """
    cfg = config or load_pipeline_config()
    source_path = Path(source_path) if source_path is not None else cfg.source_xlsx_path
    raw_dir = Path(raw_dir) if raw_dir is not None else cfg.raw_data_dir

    if not source_path.exists():
        raise IngestionError(f"Source file not found: {source_path}")

    columns = _read_header_columns(source_path)
    _validate_required_columns(columns)

    source_sha256 = compute_sha256(source_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source_path.name
    sidecar_path = _checksum_sidecar(raw_path)

    # Source file is already the canonical raw copy (same resolved path) — nothing to copy.
    if raw_path.resolve() == source_path.resolve():
        sidecar_path.write_text(source_sha256, encoding="utf-8")
        logger.info("Source is already the raw copy at %s; verified in place.", raw_path)
        return IngestedFile(source_path, raw_path, source_sha256, was_copied=False)

    if raw_path.exists():
        existing_sha256 = compute_sha256(raw_path)

        if existing_sha256 == source_sha256:
            logger.info(
                "Raw copy already present and checksum-verified at %s; skipping copy.",
                raw_path,
            )
            if not sidecar_path.exists():
                sidecar_path.write_text(existing_sha256, encoding="utf-8")
            return IngestedFile(source_path, raw_path, existing_sha256, was_copied=False)

        if not force:
            raise IngestionError(
                f"A raw copy already exists at {raw_path} with a different checksum "
                f"(existing={existing_sha256}, source={source_sha256}). Refusing to "
                f"overwrite an existing raw file. Pass force=True to replace it "
                f"deliberately."
            )

        logger.warning(
            "Overwriting existing raw copy at %s (checksum mismatch, force=True).",
            raw_path,
        )

    shutil.copy2(source_path, raw_path)
    sidecar_path.write_text(source_sha256, encoding="utf-8")
    logger.info("Copied source file to raw copy: %s -> %s", source_path, raw_path)

    return IngestedFile(source_path, raw_path, source_sha256, was_copied=True)


def load_dataset(ingested: IngestedFile) -> pd.DataFrame:
    """Load the full dataset from the verified raw copy. Called once per pipeline run."""
    logger.info("Loading dataset from %s", ingested.raw_path)
    df = pd.read_excel(ingested.raw_path, sheet_name=SHEET_NAME)
    logger.info("Loaded %d rows x %d columns", *df.shape)
    return df
