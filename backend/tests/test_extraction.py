import asyncio

from backend.app.core.config import Settings
from backend.app.schemas.document import DocumentType, FileValidation
from backend.app.services.document_validation_service import ValidatedDocument
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.ocr_service import TextExtraction, TextPage


def test_native_text_fallback_extracts_grounded_key_values():
    service = ExtractionService(Settings(gemini_api_key=None))
    document = ValidatedDocument(
        name="native.pdf",
        data=b"",
        mime_type="application/pdf",
        page_count=1,
        validation=FileValidation(),
    )
    text = TextExtraction(
        pages=[
            TextPage(
                page_number=1,
                text="Tax Invoice\nInvoice Number: INV-1\nSubtotal: USD 100.00\nTotal: USD 105.00",
            )
        ],
        has_text_layer=True,
    )
    result = asyncio.run(service.extract(DocumentType.invoice, document, text))
    values = {field.key: field.value for field in result.fields}
    assert values["invoice_number"] == "INV-1"
    assert values["subtotal"] == 100.0
    assert values["total"] == 105.0
    assert all(field.evidence.page_number == 1 for field in result.fields)


def test_fenced_structured_response_is_parsed():
    fence = chr(96) * 3
    result = ExtractionService._parse_json(
        fence + 'json\n{"fields": [], "tables": []}\n' + fence
    )
    assert result == {"fields": [], "tables": []}


def test_evidence_confidence_is_deterministic():
    payload = {
        "document_title": "Invoice",
        "currency": "USD",
        "periods": [],
        "fields": [
            {
                "key": "total_amount",
                "label": "Total",
                "value": 10,
                "raw_value": "10.00",
                "data_type": "number",
                "period": None,
                "section": "totals",
                "source_text": "Total 10.00",
                "page_number": 1,
            }
        ],
        "tables": [],
    }
    result = ExtractionService._normalize_result(payload)
    ExtractionService._assign_evidence_confidence(result)
    assert result.fields[0].confidence == 0.98
