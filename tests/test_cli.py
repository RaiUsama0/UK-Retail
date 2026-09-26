from ecommerce_analytics.cli import run_ingestion_pipeline


def test_run_ingestion_pipeline_end_to_end(tmp_path, sample_df, write_sample_xlsx, monkeypatch):
    source = write_sample_xlsx(tmp_path / "Online Retail.xlsx")
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"
    reports_dir = tmp_path / "reports"

    monkeypatch.setenv("SOURCE_XLSX_PATH", str(source))
    monkeypatch.setenv("RAW_DATA_DIR", str(raw_dir))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(processed_dir))
    monkeypatch.setenv("REPORTS_DIR", str(reports_dir))

    result = run_ingestion_pipeline()

    assert result.row_count == 8
    assert result.duplicate_rows == 1
    assert result.was_copied is True
    assert result.json_report_path.exists()
    assert result.markdown_report_path.exists()

    # Re-running should verify checksum in place rather than re-copying.
    second = run_ingestion_pipeline()
    assert second.was_copied is False
