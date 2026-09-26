import pytest

from ecommerce_analytics.ingestion import (
    IngestionError,
    compute_sha256,
    ingest_raw_file,
    load_dataset,
)


def test_ingest_success_copies_file_and_loads(tmp_path, write_sample_xlsx):
    source = write_sample_xlsx(tmp_path / "source" / "Online Retail.xlsx")
    raw_dir = tmp_path / "raw"

    result = ingest_raw_file(source_path=source, raw_dir=raw_dir)

    assert result.was_copied is True
    assert result.raw_path.exists()
    assert result.raw_path.read_bytes() == source.read_bytes()
    assert result.sha256 == compute_sha256(source)

    df = load_dataset(result)
    assert len(df) == 8


def test_ingest_missing_file_raises(tmp_path):
    with pytest.raises(IngestionError, match="not found"):
        ingest_raw_file(source_path=tmp_path / "does_not_exist.xlsx", raw_dir=tmp_path / "raw")


def test_ingest_corrupt_file_raises(tmp_path):
    corrupt = tmp_path / "Online Retail.xlsx"
    corrupt.write_bytes(b"this is not a real xlsx file")

    with pytest.raises(IngestionError, match="could not be read"):
        ingest_raw_file(source_path=corrupt, raw_dir=tmp_path / "raw")


def test_ingest_missing_required_column_raises(tmp_path, sample_df, write_sample_xlsx):
    broken_df = sample_df.drop(columns=["CustomerID"])
    source = write_sample_xlsx(tmp_path / "Online Retail.xlsx", df=broken_df)

    with pytest.raises(IngestionError, match="missing required column"):
        ingest_raw_file(source_path=source, raw_dir=tmp_path / "raw")


def test_ingest_skips_redundant_copy_when_checksum_matches(tmp_path, write_sample_xlsx):
    source = write_sample_xlsx(tmp_path / "source" / "Online Retail.xlsx")
    raw_dir = tmp_path / "raw"

    first = ingest_raw_file(source_path=source, raw_dir=raw_dir)
    assert first.was_copied is True

    second = ingest_raw_file(source_path=source, raw_dir=raw_dir)
    assert second.was_copied is False
    assert second.sha256 == first.sha256


def test_ingest_refuses_overwrite_on_checksum_mismatch(tmp_path, write_sample_xlsx, sample_df):
    source = write_sample_xlsx(tmp_path / "source" / "Online Retail.xlsx")
    raw_dir = tmp_path / "raw"
    ingest_raw_file(source_path=source, raw_dir=raw_dir)

    # Simulate the raw copy having drifted from the source (e.g. manual edit).
    different_df = sample_df.copy()
    different_df["Quantity"] = different_df["Quantity"] + 1
    write_sample_xlsx(raw_dir / "Online Retail.xlsx", df=different_df)

    with pytest.raises(IngestionError, match="Refusing to overwrite"):
        ingest_raw_file(source_path=source, raw_dir=raw_dir)

    # With force=True, the overwrite is allowed.
    result = ingest_raw_file(source_path=source, raw_dir=raw_dir, force=True)
    assert result.was_copied is True
    assert result.raw_path.read_bytes() == source.read_bytes()


def test_ingest_source_already_in_raw_dir_verifies_in_place(tmp_path, write_sample_xlsx):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = write_sample_xlsx(raw_dir / "Online Retail.xlsx")

    result = ingest_raw_file(source_path=source, raw_dir=raw_dir)

    assert result.was_copied is False
    assert result.raw_path == source
