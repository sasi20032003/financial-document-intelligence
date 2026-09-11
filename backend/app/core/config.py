"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    default_database_path = (
        Path("/tmp") / "document_intelligence.db"
        if os.getenv("VERCEL")
        else PROJECT_ROOT / "data" / "document_intelligence.db"
    )
    value = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{default_database_path.as_posix()}",
    )
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://") and "+" not in value.split("://", 1)[0]:
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Financial Document Intelligence")
    app_version: str = "1.0.0"
    environment: str = os.getenv("APP_ENV", "development")
    database_url: str = _database_url()
    dataset_directory: Path = Path(
        os.getenv("DATASET_DIRECTORY", str(PROJECT_ROOT / "New Dataset"))
    ).resolve()
    dataset_files_per_type: int = _as_int("DATASET_FILES_PER_TYPE", 2)
    seed_demo_data: bool = _as_bool("SEED_DEMO_DATA", bool(os.getenv("VERCEL")))
    max_file_size_bytes: int = _as_int("MAX_FILE_SIZE_MB", 10) * 1024 * 1024
    max_pages: int = _as_int("MAX_DOCUMENT_PAGES", 3)
    financial_tolerance: float = _as_float("FINANCIAL_TOLERANCE", 0.01)
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    gemini_api_base: str = os.getenv(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
    )
    gemini_api_revision: str = os.getenv("GEMINI_API_REVISION", "2026-05-20")
    model_timeout_seconds: int = _as_int("MODEL_TIMEOUT_SECONDS", 90)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()
