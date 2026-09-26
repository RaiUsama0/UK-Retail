"""Centralised configuration loaded from environment variables / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repo root = two levels up from this file (src/ecommerce_analytics/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True)
class PipelineConfig:
    raw_data_dir: Path
    processed_data_dir: Path
    source_xlsx_path: Path


def _get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and set it."
        )
    return value


def load_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=_get_env("POSTGRES_HOST", "localhost"),
        port=int(_get_env("POSTGRES_PORT", "5433")),
        name=_get_env("POSTGRES_DB", "ecommerce_analytics"),
        user=_get_env("POSTGRES_USER", "analytics_user"),
        password=_get_env("POSTGRES_PASSWORD", "change_me_locally"),
    )


def load_pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        raw_data_dir=REPO_ROOT / _get_env("RAW_DATA_DIR", "data/raw"),
        processed_data_dir=REPO_ROOT / _get_env("PROCESSED_DATA_DIR", "data/processed"),
        source_xlsx_path=REPO_ROOT / _get_env("SOURCE_XLSX_PATH", "Online Retail.xlsx"),
    )
