"""End-to-end orchestration for validation, extraction, reconciliation, and storage."""

from __future__ import annotations

import logging
from time import perf_counter

from backend.app.core.exceptions import ExtractionError
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentResult,
    DocumentType,
    FinancialCheck,
    FinancialValidation,
    ProcessingMetadata,
    ProcessingStatus,
    ValidationStatus,
)
from backend.app.schemas.extraction import ExtractionResult
from backend.app.services.document_validation_service import DocumentValidationService
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.financial_validation_service import FinancialValidationService
from backend.app.services.ocr_service import OcrService


logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        document_validator: DocumentValidationService,
        ocr_service: OcrService,
        extraction_service: ExtractionService,
        financial_validator: FinancialValidationService,
    ) -> None:
        self.repository = repository
        self.document_validator = document_validator
        self.ocr_service = ocr_service
        self.extraction_service = extraction_service
        self.financial_validator = financial_validator

    async def process(
        self,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        document_type: DocumentType,
    ) -> DocumentResult:
        started = perf_counter()
        document = self.document_validator.validate(filename, content_type, data)
        logger.info(
            "Document validated",
            extra={
                "document": document.name,
                "document_type": document_type.value,
                "pages": document.page_count,
            },
        )
        text = self.ocr_service.extract_text_layer(document)
        ocr_used = not text.has_text_layer
        try:
            extraction = await self.extraction_service.extract(
                document_type, document, text
            )
            validation = self.financial_validator.validate(document_type, extraction)
            confidences = [
                field.confidence
                for field in extraction.fields
                if field.confidence is not None
            ]
            overall_confidence = (
                round(sum(confidences) / len(confidences), 2)
                if confidences
                else None
            )
            result = DocumentResult(
                document_name=document.name,
                document_type=document_type,
                processing_status=ProcessingStatus.PASS,
                overall_confidence=overall_confidence,
                file_validation=document.validation,
                extracted_data=extraction,
                validation=validation,
                processing_metadata=ProcessingMetadata(
                    ocr_used=ocr_used,
                    extraction_provider=self.extraction_service.provider_name,
                    processing_time_ms=int((perf_counter() - started) * 1000),
                ),
            )
            self.repository.save(result)
            logger.info(
                "Document processing completed",
                extra={
                    "document": document.name,
                    "validation_status": validation.overall_status.value,
                },
            )
            return result
        except ExtractionError as exc:
            elapsed = int((perf_counter() - started) * 1000)
            failed = DocumentResult(
                document_name=document.name,
                document_type=document_type,
                processing_status=ProcessingStatus.FAILED,
                file_validation=document.validation,
                extracted_data=ExtractionResult(),
                validation=FinancialValidation(
                    checks=[
                        FinancialCheck(
                            name="financial_validation",
                            formula="Required financial relationship",
                            status=ValidationStatus.NOT_APPLICABLE,
                            notes="Extraction did not complete.",
                        )
                    ],
                    overall_status=ValidationStatus.NOT_APPLICABLE,
                    issues=[exc.message],
                ),
                processing_metadata=ProcessingMetadata(
                    ocr_used=ocr_used,
                    extraction_provider=self.extraction_service.provider_name,
                    processing_time_ms=elapsed,
                    error_code=exc.code,
                ),
            )
            self.repository.save(failed)
            logger.warning(
                "Document extraction failed",
                extra={"document": document.name, "error_code": exc.code},
            )
            raise

    def get(self, document_name: str) -> DocumentResult | None:
        return self.repository.get_by_name(document_name)

    def list(
        self, limit: int = 50, offset: int = 0, query: str | None = None
    ) -> DocumentListResponse:
        return self.repository.list(limit=limit, offset=offset, query=query)
