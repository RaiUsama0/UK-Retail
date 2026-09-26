from ecommerce_analytics.config import load_database_config, load_pipeline_config


def test_database_config_defaults():
    cfg = load_database_config()
    assert cfg.host
    assert cfg.port > 0
    assert cfg.sqlalchemy_url.startswith("postgresql+psycopg://")


def test_pipeline_config_paths_are_absolute():
    cfg = load_pipeline_config()
    assert cfg.raw_data_dir.is_absolute()
    assert cfg.processed_data_dir.is_absolute()
    assert cfg.source_xlsx_path.name == "Online Retail.xlsx"
