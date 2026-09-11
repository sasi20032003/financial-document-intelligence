"""Structured extraction through Gemini vision with a native-text fallback."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx

from backend.app.core.config import Settings
from backend.app.core.exceptions import ExtractionError
from backend.app.schemas.document import DocumentType
from backend.app.schemas.extraction import Evidence, ExtractedField, ExtractedTable, ExtractionResult
from backend.app.services.document_validation_service import ValidatedDocument
from backend.app.services.ocr_service import TextExtraction


logger = logging.getLogger(__name__)


EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_title": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "periods": {"type": "array", "items": {"type": "string"}},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                    "value": {"type": ["string", "number", "boolean", "null"]},
                    "raw_value": {"type": ["string", "null"]},
                    "data_type": {
                        "type": "string",
                        "enum": ["string", "number", "date", "currency", "percentage", "identifier", "boolean", "unknown"],
                    },
                    "period": {"type": ["string", "null"]},
                    "section": {"type": ["string", "null"]},
                    "source_text": {"type": ["string", "null"]},
                    "page_number": {"type": ["integer", "null"]},
                },
                "required": ["key", "label", "value", "raw_value", "data_type", "period", "section", "source_text", "page_number"],
            },
        },
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "page_number": {"type": ["integer", "null"]},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "rows": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": ["string", "null"]}},
                    },
                },
                "required": ["name", "title", "page_number", "columns", "rows"],
            },
        },
    },
    "required": ["document_title", "currency", "periods", "fields", "tables"],
}


DOCUMENT_MINIMUMS = {
    DocumentType.invoice: (
        "invoice_number, invoice_date, vendor_name, customer_name, currency, subtotal, "
        "tax_amount, discount, total_amount, payment details, and every line item"
    ),
    DocumentType.balance_sheet: (
        "statement headers, every period, currency, every asset, liability, and equity line, "
        "total_assets, total_liabilities, total_equity, and total_capital_and_liabilities"
    ),
    DocumentType.profit_and_loss: (
        "statement headers, every period, currency, every income and expense line, interest_earned, "
        "other_income, total_income, interest_expended, operating_expenses, provisions_and_contingencies, "
        "total_expenditure, profit before minority interest, minority interest, attributable profit, "
        "current profit, brought forward profit, and total available for appropriation"
    ),
    DocumentType.cash_flow_statement: (
        "statement headers, every period, currency, every cash-flow line, operating_cash_flow, "
        "investing_cash_flow, financing_cash_flow, fx_translation_adjustment, net_change_in_cash, "
        "opening_cash, acquisition or amalgamation adjustments, and closing_cash"
    ),
}


class ExtractionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def provider_name(self) -> str:
        return "gemini" if self.settings.gemini_api_key else "local_text"

    async def extract(
        self,
        document_type: DocumentType,
        document: ValidatedDocument,
        text: TextExtraction,
    ) -> ExtractionResult:
        if self.settings.gemini_api_key:
            result = await self._extract_with_gemini(document_type, document)
        elif text.has_text_layer:
            result = self._extract_from_native_text(document_type, text)
        else:
            raise ExtractionError(
                "EXTRACTION_PROVIDER_NOT_CONFIGURED",
                "This scanned document requires GEMINI_API_KEY for multimodal OCR and extraction.",
                503,
            )
        if not result.fields and not result.tables:
            raise ExtractionError(
                "NO_CONTENT_EXTRACTED",
                "No meaningful fields or tables could be extracted from the document.",
                422,
            )
        self._assign_evidence_confidence(result)
        return result

    async def _extract_with_gemini(
        self, document_type: DocumentType, document: ValidatedDocument
    ) -> ExtractionResult:
        media_type = "document" if document.mime_type == "application/pdf" else "image"
        payload = {
            "model": self.settings.gemini_model,
            "input": [
                {"type": "text", "text": self._prompt(document_type)},
                {
                    "type": media_type,
                    "data": base64.b64encode(document.data).decode("ascii"),
                    "mime_type": document.mime_type,
                },
            ],
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": EXTRACTION_SCHEMA,
            },
        }
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key or "",
            "Content-Type": "application/json",
        }
        if self.settings.gemini_api_revision:
            headers["Api-Revision"] = self.settings.gemini_api_revision
        url = f"{self.settings.gemini_api_base.rstrip('/')}/interactions"
        logger.info(
            "Calling Gemini extraction",
            extra={
                "document": document.name,
                "document_type": document_type.value,
                "model": self.settings.gemini_model,
            },
        )
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.model_timeout_seconds)
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            parsed = self._parse_json(self._response_text(response.json()))
            return self._normalize_result(parsed)
        except httpx.TimeoutException as exc:
            raise ExtractionError(
                "MODEL_TIMEOUT", "The extraction model timed out. Please try again.", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Gemini extraction request failed",
                extra={"status_code": exc.response.status_code},
            )
            raise ExtractionError(
                "MODEL_API_ERROR",
                "The extraction provider could not process the document.",
                502,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Gemini connection failed", extra={"error_type": type(exc).__name__})
            raise ExtractionError(
                "MODEL_CONNECTION_ERROR",
                "The extraction provider is temporarily unreachable.",
                502,
            ) from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.exception("Gemini returned an invalid structured response")
            raise ExtractionError(
                "INVALID_MODEL_RESPONSE",
                "The extraction provider returned an invalid structured response.",
                502,
            ) from exc

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        for step in reversed(response.get("steps", [])):
            for content in step.get("content", []):
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    return content["text"]
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if isinstance(part.get("text"), str):
                    return part["text"]
        raise ValueError("Response does not contain text output")

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        cleaned = raw_text.strip()
        fence = chr(96) * 3
        if cleaned.startswith(fence):
            cleaned = cleaned.removeprefix(fence + "json").removeprefix(fence)
            cleaned = cleaned.removesuffix(fence).strip()
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            raise ValueError("Structured response root must be an object")
        return value

    @staticmethod
    def _normalize_result(payload: dict[str, Any]) -> ExtractionResult:
        fields: list[ExtractedField] = []
        for source_item in payload.get("fields") or []:
            if not isinstance(source_item, dict):
                continue
            item = dict(source_item)
            evidence = Evidence(
                source_text=item.pop("source_text", None),
                page_number=item.pop("page_number", None),
            )
            fields.append(ExtractedField(**item, evidence=evidence))
        tables = [
            ExtractedTable.model_validate(table)
            for table in (payload.get("tables") or [])
            if isinstance(table, dict)
        ]
        return ExtractionResult(
            document_title=payload.get("document_title"),
            currency=payload.get("currency"),
            periods=[str(period) for period in (payload.get("periods") or [])],
            fields=fields,
            tables=tables,
        )

    @staticmethod
    def _assign_evidence_confidence(result: ExtractionResult) -> None:
        uncertain = re.compile(r"(?:illegible|unclear|uncertain|unreadable|\?{2,})", re.I)
        for field in result.fields:
            if field.value is None:
                field.confidence = 0.0
                continue
            score = 0.80
            score += 0.10 if field.evidence.source_text else 0
            score += 0.05 if field.evidence.page_number else 0
            score += 0.03 if field.raw_value is not None else 0
            if uncertain.search(str(field.value)) or uncertain.search(field.raw_value or ""):
                score -= 0.30
            field.confidence = round(max(0.0, min(score, 0.98)), 2)

    def _prompt(self, document_type: DocumentType) -> str:
        return f"""You are a financial-document transcription engine. The caller selected document_type={document_type.value}; do not classify it.

Extract every meaningful visible value and every table cell from every page. Minimum coverage includes {DOCUMENT_MINIMUMS[document_type]}; this is a floor, not a field limit.

Rules:
1. Transcribe only what the pixels support; never infer or invent.
2. Return null for a visible missing or unreadable value.
3. Preserve exact raw_value and source_text. Normalize numbers in value and treat parentheses or brackets around amounts as negative.
4. Use stable snake_case keys. Repeat keys for comparative periods and set period.
5. Put each financial line item in fields and its visible table. Set section to a useful group such as assets, capital_and_liabilities, income, expenditure, appropriation, operating, investing, financing, or cash_reconciliation.
6. Include page_number for every grounded value where possible.
7. For tables, preserve visual column order and return same-length row arrays. Do not omit subtotal, total, note-reference, comparative-period, tax, or discount columns.
8. For invoices, name the item table line_items and extract quantity, unit_price, and amount columns whenever present. Include tax_included only when the document explicitly says so.
9. Do not validate. Deterministic code performs financial validation."""

    def _extract_from_native_text(
        self, document_type: DocumentType, text: TextExtraction
    ) -> ExtractionResult:
        fields: list[ExtractedField] = []
        title: str | None = None
        key_counts: dict[str, int] = {}
        for page in text.pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            if title is None and lines:
                title = lines[0][:200]
            for line in lines:
                pair = self._split_label_value(line)
                if pair is None:
                    continue
                label, raw_value = pair
                key = self._slug(label)
                key_counts[key] = key_counts.get(key, 0) + 1
                unique_key = key if key_counts[key] == 1 else f"{key}_{key_counts[key]}"
                value, data_type = self._normalize_value(raw_value)
                fields.append(
                    ExtractedField(
                        key=unique_key,
                        label=label,
                        value=value,
                        raw_value=raw_value,
                        data_type=data_type,
                        evidence=Evidence(source_text=line, page_number=page.page_number),
                    )
                )
        logger.info(
            "Used native-text fallback",
            extra={"document_type": document_type.value, "field_count": len(fields)},
        )
        return ExtractionResult(document_title=title, fields=fields)

    @staticmethod
    def _split_label_value(line: str) -> tuple[str, str] | None:
        colon_match = re.match(r"^(.{2,80}?):\s*(\S.+)$", line)
        if colon_match:
            return colon_match.group(1).strip(), colon_match.group(2).strip()
        spaced = re.split(r"\s{2,}", line)
        if len(spaced) >= 2 and re.search(r"\d", spaced[-1]):
            return " ".join(spaced[:-1]).strip(), spaced[-1].strip()
        return None

    @staticmethod
    def _slug(value: str) -> str:
        key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return key[:80] or "field"

    @staticmethod
    def _normalize_value(raw: str) -> tuple[Any, str]:
        candidate = raw.strip()
        negative = candidate.startswith("(") and candidate.endswith(")")
        numeric_source = re.sub(r"^[A-Z]{3}\s+", "", candidate)
        numeric = re.sub(r"[^0-9.\-]", "", numeric_source.replace(",", ""))
        if numeric and not re.search(r"[A-Za-z]", numeric_source) and re.fullmatch(r"-?\d+(?:\.\d+)?", numeric):
            value = float(numeric)
            if negative:
                value = -abs(value)
            return value, "number"
        return candidate, "string"
