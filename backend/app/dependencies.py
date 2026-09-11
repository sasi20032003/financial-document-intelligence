"""FastAPI dependency graph for replaceable application services."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_db
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.services.document_service import DocumentService
from backend.app.services.document_validation_service import DocumentValidationService
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.financial_validation_service import FinancialValidationService
from backend.app.services.ocr_service import OcrService


@lru_cache
def get_extraction_service() -> ExtractionService:
    return ExtractionService(get_settings())


@lru_cache
def get_ocr_service() -> OcrService:
    return OcrService()


def get_document_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    extraction_service: ExtractionService = Depends(get_extraction_service),
    ocr_service: OcrService = Depends(get_ocr_service),
) -> DocumentService:
    return DocumentService(
        repository=DocumentRepository(session),
        document_validator=DocumentValidationService(settings),
        ocr_service=ocr_service,
        extraction_service=extraction_service,
        financial_validator=FinancialValidationService(settings.financial_tolerance),
    )
