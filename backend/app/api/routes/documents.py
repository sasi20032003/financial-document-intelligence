"""Document processing, dataset import, lookup, listing, and health endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_db
from backend.app.core.exceptions import AppError
from backend.app.dependencies import get_document_service
from backend.app.schemas.document import (
    DatasetDocument,
    DatasetManifest,
    DatasetProcessRequest,
    DocumentListResponse,
    DocumentResult,
    DocumentType,
    ErrorResponse,
    HealthResponse,
    ProcessingStatus,
)
from backend.app.services.document_service import DocumentService
from backend.app.services.document_validation_service import ALLOWED_EXTENSIONS


router = APIRouter(prefix="/api/v1", tags=["documents"])

DATASET_FOLDER_TYPES = {
    "invoices": DocumentType.invoice,
    "balance sheet": DocumentType.balance_sheet,
    "profit & loss": DocumentType.profit_and_loss,
    "cash flows": DocumentType.cash_flow_statement,
}


def _dataset_document_type(relative_path: Path) -> DocumentType | None:
    for part in relative_path.parts[:-1]:
        document_type = DATASET_FOLDER_TYPES.get(part.casefold())
        if document_type is not None:
            return document_type
    return None


def _dataset_manifest(
    settings: Settings, service: DocumentService
) -> DatasetManifest:
    root = settings.dataset_directory.resolve()
    if not root.is_dir():
        return DatasetManifest(
            available=False, total=0, processed=0, remaining=0, items=[]
        )

    stored = {
        item.document_name: item.processing_status
        for item in service.list(limit=200).items
    }
    items: list[DatasetDocument] = []
    for source_path in root.rglob("*"):
        if not source_path.is_file() or source_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            resolved_path = source_path.resolve()
            relative_path = resolved_path.relative_to(root)
            size_bytes = resolved_path.stat().st_size
        except (OSError, ValueError):
            continue
        document_type = _dataset_document_type(relative_path)
        if document_type is None:
            continue
        status = stored.get(resolved_path.name)
        items.append(
            DatasetDocument(
                relative_path=relative_path.as_posix(),
                document_name=resolved_path.name,
                document_type=document_type,
                size_bytes=size_bytes,
                processing_status=status,
                already_processed=status == ProcessingStatus.PASS,
            )
        )

    curated_items: list[DatasetDocument] = []
    per_type_limit = max(settings.dataset_files_per_type, 0)
    for document_type in DocumentType:
        matching_items = [
            item for item in items if item.document_type == document_type
        ]
        matching_items.sort(
            key=lambda item: item.document_name.casefold(), reverse=True
        )
        curated_items.extend(matching_items[:per_type_limit])
    items = curated_items
    items.sort(key=lambda item: (item.document_type.value, item.document_name.casefold()))
    processed = sum(item.already_processed for item in items)
    return DatasetManifest(
        available=True,
        total=len(items),
        processed=processed,
        remaining=len(items) - processed,
        items=items,
    )


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as source_file:
        return source_file.read(limit + 1)


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> HealthResponse:
    session.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        database="ok",
        extraction_provider_configured=bool(settings.gemini_api_key),
    )


@router.post(
    "/documents/process",
    response_model=DocumentResult,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def process_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> DocumentResult:
    data = await file.read(settings.max_file_size_bytes + 1)
    await file.close()
    return await service.process(file.filename, file.content_type, data, document_type)


@router.get("/dataset", response_model=DatasetManifest)
def list_dataset(
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> DatasetManifest:
    return _dataset_manifest(settings, service)


@router.post(
    "/dataset/process",
    response_model=DocumentResult,
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def process_dataset_document(
    payload: DatasetProcessRequest,
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_settings),
) -> DocumentResult:
    root = settings.dataset_directory.resolve()
    if not root.is_dir():
        raise AppError(
            "DATASET_NOT_FOUND",
            "The configured local dataset directory is unavailable.",
            404,
        )

    relative_path = Path(payload.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise AppError("INVALID_DATASET_PATH", "The dataset path is invalid.", 400)
    candidate = (root / relative_path).resolve()
    try:
        safe_relative_path = candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(
            "INVALID_DATASET_PATH", "The dataset path is invalid.", 400
        ) from exc
    if not candidate.is_file():
        raise AppError(
            "DATASET_FILE_NOT_FOUND", "The dataset file was not found.", 404
        )

    document_type = _dataset_document_type(safe_relative_path)
    content_type = ALLOWED_EXTENSIONS.get(candidate.suffix.lower())
    if document_type is None or content_type is None:
        raise AppError(
            "UNSUPPORTED_DATASET_FILE",
            "The dataset file is not in a supported document-type folder.",
            415,
        )

    existing = service.get(candidate.name)
    if (
        existing is not None
        and existing.processing_status == ProcessingStatus.PASS
        and not payload.force
    ):
        return existing

    data = await asyncio.to_thread(
        _read_limited, candidate, settings.max_file_size_bytes
    )
    return await service.process(
        candidate.name, content_type, data, document_type
    )


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=100),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    return service.list(limit=limit, offset=offset, query=q)


@router.get(
    "/documents/{document_name}",
    response_model=DocumentResult,
    responses={404: {"model": ErrorResponse}},
)
def get_document(
    document_name: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResult:
    safe_name = Path(document_name).name
    result = service.get(safe_name)
    if result is None:
        raise AppError(
            "DOCUMENT_NOT_FOUND",
            f"No processed result was found for '{safe_name}'.",
            404,
        )
    return result
