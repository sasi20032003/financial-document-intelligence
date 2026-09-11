"""Local text-layer extraction kept separate from AI field extraction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from backend.app.services.document_validation_service import ValidatedDocument


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextExtraction:
    pages: list[TextPage]
    has_text_layer: bool

    @property
    def combined_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text.strip())


class OcrService:
    """Reads native PDF text; Gemini performs native OCR for scans and images."""

    def extract_text_layer(self, document: ValidatedDocument) -> TextExtraction:
        if document.mime_type != "application/pdf":
            return TextExtraction(
                pages=[TextPage(page_number=1, text="")], has_text_layer=False
            )

        reader = PdfReader(BytesIO(document.data), strict=False)
        pages: list[TextPage] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                logger.warning("PDF text-layer extraction failed", extra={"page": index})
                text = ""
            pages.append(TextPage(page_number=index, text=text.strip()))
        total_characters = sum(len(page.text) for page in pages)
        return TextExtraction(pages=pages, has_text_layer=total_characters >= 40)
