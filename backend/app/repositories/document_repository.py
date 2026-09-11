"""Database access for the latest result of each document name."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import PersistenceError
from backend.app.models.document import DocumentRecord
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentResult,
    DocumentSummary,
)


logger = logging.getLogger(__name__)


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, result: DocumentResult) -> DocumentResult:
        try:
            record = self.session.scalar(
                select(DocumentRecord).where(
                    DocumentRecord.document_name == result.document_name
                )
            )
            if record is None:
                record = DocumentRecord(document_name=result.document_name)
                self.session.add(record)

            record.document_type = result.document_type.value
            record.processing_status = result.processing_status.value
            record.validation_status = result.validation.overall_status.value
            record.overall_confidence = result.overall_confidence
            record.file_validation_json = result.file_validation.model_dump_json()
            record.extracted_data_json = result.extracted_data.model_dump_json()
            record.validation_json = result.validation.model_dump_json()
            record.processing_metadata_json = result.processing_metadata.model_dump_json()
            record.processed_at = result.processing_metadata.processed_at
            self.session.commit()
            self.session.refresh(record)
            return result
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.exception("Database write failed", extra={"document": result.document_name})
            raise PersistenceError(
                "DATABASE_WRITE_FAILED",
                "The processed result could not be stored.",
                503,
            ) from exc

    def get_by_name(self, document_name: str) -> DocumentResult | None:
        try:
            record = self.session.scalar(
                select(DocumentRecord).where(
                    DocumentRecord.document_name == document_name
                )
            )
            return self._to_result(record) if record else None
        except SQLAlchemyError as exc:
            logger.exception("Database read failed", extra={"document": document_name})
            raise PersistenceError(
                "DATABASE_READ_FAILED", "Stored results are temporarily unavailable.", 503
            ) from exc

    def list(self, limit: int, offset: int, query: str | None) -> DocumentListResponse:
        try:
            filters = []
            if query:
                token = f"%{query.strip()}%"
                filters.append(
                    or_(
                        DocumentRecord.document_name.ilike(token),
                        DocumentRecord.document_type.ilike(token),
                        DocumentRecord.processing_status.ilike(token),
                    )
                )

            count_statement = select(func.count(DocumentRecord.id))
            list_statement = select(DocumentRecord)
            if filters:
                count_statement = count_statement.where(*filters)
                list_statement = list_statement.where(*filters)

            total = int(self.session.scalar(count_statement) or 0)
            records = self.session.scalars(
                list_statement.order_by(DocumentRecord.processed_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            items = [
                DocumentSummary(
                    document_name=record.document_name,
                    document_type=record.document_type,
                    processing_status=record.processing_status,
                    validation_status=record.validation_status,
                    overall_confidence=record.overall_confidence,
                    processed_at=record.processed_at,
                )
                for record in records
            ]
            return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)
        except SQLAlchemyError as exc:
            logger.exception("Database list failed")
            raise PersistenceError(
                "DATABASE_READ_FAILED", "Stored results are temporarily unavailable.", 503
            ) from exc

    @staticmethod
    def _to_result(record: DocumentRecord) -> DocumentResult:
        return DocumentResult(
            document_name=record.document_name,
            document_type=record.document_type,
            processing_status=record.processing_status,
            overall_confidence=record.overall_confidence,
            file_validation=json.loads(record.file_validation_json),
            extracted_data=json.loads(record.extracted_data_json),
            validation=json.loads(record.validation_json),
            processing_metadata=json.loads(record.processing_metadata_json),
        )
