"""Request and response contracts for document processing."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.extraction import ExtractionResult


class DocumentType(str, Enum):
    invoice = "invoice"
    balance_sheet = "balance_sheet"
    profit_and_loss = "profit_and_loss"
    cash_flow_statement = "cash_flow_statement"


class ProcessingStatus(str, Enum):
    PASS = "PASS"
    FAILED = "FAILED"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FileValidation(BaseModel):
    file_type: str | None = None
    is_supported: bool = False
    is_readable: bool = False
    page_count: int | None = None
    size_bytes: int = 0
    status: ProcessingStatus = ProcessingStatus.FAILED


class FinancialCheck(BaseModel):
    name: str
    formula: str
    period: str | None = None
    operands: dict[str, float | None] = Field(default_factory=dict)
    calculated_value: float | None = None
    reported_value: float | None = None
    variance: float | None = None
    status: ValidationStatus
    notes: str | None = None


class FinancialValidation(BaseModel):
    checks: list[FinancialCheck] = Field(default_factory=list)
    overall_status: ValidationStatus = ValidationStatus.NOT_APPLICABLE
    issues: list[str] = Field(default_factory=list)


class ProcessingMetadata(BaseModel):
    ocr_used: bool = False
    extraction_provider: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_ms: int = 0
    error_code: str | None = None


class DocumentResult(BaseModel):
    document_name: str
    document_type: DocumentType
    processing_status: ProcessingStatus
    overall_confidence: float | None = Field(default=None, ge=0, le=1)
    file_validation: FileValidation
    extracted_data: ExtractionResult
    validation: FinancialValidation
    processing_metadata: ProcessingMetadata


class DocumentSummary(BaseModel):
    document_name: str
    document_type: DocumentType
    processing_status: ProcessingStatus
    validation_status: ValidationStatus
    overall_confidence: float | None = None
    processed_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int
    limit: int
    offset: int


class DatasetDocument(BaseModel):
    relative_path: str
    document_name: str
    document_type: DocumentType
    size_bytes: int
    processing_status: ProcessingStatus | None = None
    already_processed: bool = False


class DatasetManifest(BaseModel):
    available: bool
    total: int
    processed: int
    remaining: int
    items: list[DatasetDocument] = Field(default_factory=list)


class DatasetProcessRequest(BaseModel):
    relative_path: str = Field(min_length=1, max_length=500)
    force: bool = False


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    extraction_provider_configured: bool
