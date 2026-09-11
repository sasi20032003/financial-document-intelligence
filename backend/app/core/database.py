"""SQLAlchemy engine, session lifecycle, and schema initialization."""

from __future__ import annotations

from collections.abc import Generator
import logging
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import PROJECT_ROOT, get_settings


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.database_url.startswith("sqlite:///"):
    database_path = settings.database_url.removeprefix("sqlite:///")
    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_database() -> None:
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        seed_demo_database()


def seed_demo_database() -> None:
    """Populate an empty hosted database with validated demo results."""
    from backend.app.models.document import DocumentRecord
    from backend.app.repositories.document_repository import DocumentRepository
    from backend.app.schemas.document import DocumentResult

    sample_paths = [
        PROJECT_ROOT / "sample_outputs" / name
        for name in (
            "invoice.json",
            "balance_sheet.json",
            "profit_and_loss.json",
            "cash_flow_statement.json",
            "failure.json",
        )
    ]
    with SessionLocal() as session:
        if session.scalar(select(func.count(DocumentRecord.id))):
            return

        repository = DocumentRepository(session)
        for sample_path in sample_paths:
            try:
                result = DocumentResult.model_validate_json(
                    sample_path.read_text(encoding="utf-8")
                )
                repository.save(result)
            except (OSError, ValueError):
                logger.exception(
                    "Could not seed demo result",
                    extra={"sample": sample_path.name},
                )


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
