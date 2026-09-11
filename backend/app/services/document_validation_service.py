"""Safe upload validation before OCR or model processing."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.app.core.config import Settings
from backend.app.core.exceptions import DocumentInputError
from backend.app.schemas.document import FileValidation, ProcessingStatus


ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@dataclass(frozen=True)
class ValidatedDocument:
    name: str
    data: bytes
    mime_type: str
    page_count: int
    validation: FileValidation


class DocumentValidationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate(
        self, filename: str | None, supplied_content_type: str | None, data: bytes
    ) -> ValidatedDocument:
        name = Path(filename or "").name.strip()
        if not name or name in {".", ".."}:
            raise DocumentInputError("MISSING_FILE_NAME", "A file name is required.", 400)
        if not data:
            raise DocumentInputError("EMPTY_FILE", "The uploaded file is empty.", 400)
        if len(data) > self.settings.max_file_size_bytes:
            limit_mb = self.settings.max_file_size_bytes // (1024 * 1024)
            raise DocumentInputError(
                "FILE_TOO_LARGE", f"The uploaded file exceeds the {limit_mb} MB limit.", 413
            )

        extension = Path(name).suffix.lower()
        expected_mime = ALLOWED_EXTENSIONS.get(extension)
        if expected_mime is None:
            raise DocumentInputError(
                "UNSUPPORTED_FILE_TYPE",
                "Only PDF, JPG, JPEG, and PNG documents are supported.",
                415,
            )

        detected_mime = self._detect_mime(data)
        if detected_mime is None:
            raise DocumentInputError(
                "CORRUPTED_FILE",
                "The file signature is not a readable PDF, JPG, or PNG document.",
                422,
            )
        if detected_mime != expected_mime:
            raise DocumentInputError(
                "FILE_TYPE_MISMATCH",
                "The file extension does not match the uploaded file content.",
                415,
            )
        if supplied_content_type and supplied_content_type not in {
            detected_mime,
            "application/octet-stream",
        }:
            raise DocumentInputError(
                "CONTENT_TYPE_MISMATCH",
                "The multipart content type does not match the uploaded file.",
                415,
            )

        page_count = self._validate_integrity(detected_mime, data)
        if page_count > self.settings.max_pages:
            raise DocumentInputError(
                "PAGE_LIMIT_EXCEEDED",
                f"Documents may contain no more than {self.settings.max_pages} pages.",
                422,
            )

        validation = FileValidation(
            file_type=detected_mime,
            is_supported=True,
            is_readable=True,
            page_count=page_count,
            size_bytes=len(data),
            status=ProcessingStatus.PASS,
        )
        return ValidatedDocument(name, data, detected_mime, page_count, validation)

    @staticmethod
    def _detect_mime(data: bytes) -> str | None:
        if data.startswith(b"%PDF-"):
            return "application/pdf"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        return None

    @staticmethod
    def _validate_integrity(mime_type: str, data: bytes) -> int:
        if mime_type == "application/pdf":
            try:
                reader = PdfReader(BytesIO(data), strict=False)
                if reader.is_encrypted and reader.decrypt("") == 0:
                    raise DocumentInputError(
                        "ENCRYPTED_PDF", "Password-protected PDFs are not supported.", 422
                    )
                page_count = len(reader.pages)
                if page_count < 1:
                    raise DocumentInputError(
                        "CORRUPTED_PDF", "The PDF contains no readable pages.", 422
                    )
                _ = reader.pages[0].mediabox
                return page_count
            except DocumentInputError:
                raise
            except (PdfReadError, ValueError, TypeError, OSError) as exc:
                raise DocumentInputError(
                    "CORRUPTED_PDF", "The PDF is corrupted or unreadable.", 422
                ) from exc

        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                page_count = int(getattr(image, "n_frames", 1))
                if width < 1 or height < 1:
                    raise ValueError("Image has invalid dimensions")
                return page_count
        except (UnidentifiedImageError, ValueError, OSError) as exc:
            raise DocumentInputError(
                "CORRUPTED_IMAGE", "The image is corrupted or unreadable.", 422
            ) from exc
