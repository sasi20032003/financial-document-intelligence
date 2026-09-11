from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import delete

TEST_DB = Path(__file__).resolve().parent / "test_document_intelligence.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ.pop("GEMINI_API_KEY", None)

from backend.app.core.database import SessionLocal
from backend.app.dependencies import get_extraction_service
from backend.app.main import app
from backend.app.models.document import DocumentRecord
from backend.app.schemas.document import DocumentType
from backend.app.schemas.extraction import (
    Evidence,
    ExtractedField,
    ExtractedTable,
    ExtractionResult,
)


def pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class StubExtractionService:
    provider_name = "test_stub"

    async def extract(self, document_type, document, text):
        if document_type == DocumentType.balance_sheet:
            return ExtractionResult(fields=[
                ExtractedField(key="total_assets", label="Total assets", value=500, data_type="number", period="2026"),
                ExtractedField(key="total_capital_and_liabilities", label="Total capital and liabilities", value=500, data_type="number", period="2026"),
            ])
        if document_type == DocumentType.profit_and_loss:
            return ExtractionResult(fields=[
                ExtractedField(key="interest_earned", label="Interest earned", value=1000, data_type="number", period="2026"),
                ExtractedField(key="other_income", label="Other income", value=200, data_type="number", period="2026"),
                ExtractedField(key="total_income", label="Total income", value=1200, data_type="number", period="2026"),
                ExtractedField(key="interest_expended", label="Interest expended", value=400, data_type="number", period="2026"),
                ExtractedField(key="operating_expenses", label="Operating expenses", value=300, data_type="number", period="2026"),
                ExtractedField(key="provisions_and_contingencies", label="Provisions", value=100, data_type="number", period="2026"),
                ExtractedField(key="total_expenditure", label="Total expenditure", value=800, data_type="number", period="2026"),
                ExtractedField(key="profit_before_minority_interest", label="Profit before minority", value=400, data_type="number", period="2026"),
            ])
        if document_type == DocumentType.cash_flow_statement:
            return ExtractionResult(fields=[
                ExtractedField(key="operating_cash_flow", label="Operating cash flow", value=500, data_type="number", period="2026"),
                ExtractedField(key="investing_cash_flow", label="Investing cash flow", value=-120, data_type="number", period="2026"),
                ExtractedField(key="financing_cash_flow", label="Financing cash flow", value=-80, data_type="number", period="2026"),
                ExtractedField(key="fx_translation_adjustment", label="FX adjustment", value=5, data_type="number", period="2026"),
                ExtractedField(key="net_change_in_cash", label="Net change", value=305, data_type="number", period="2026"),
                ExtractedField(key="opening_cash", label="Opening cash", value=1000, data_type="number", period="2026"),
                ExtractedField(key="other_cash_adjustments", label="Other adjustments", value=0, data_type="number", period="2026"),
                ExtractedField(key="closing_cash", label="Closing cash", value=1305, data_type="number", period="2026"),
            ])
        return ExtractionResult(
            document_title="Test Invoice",
            currency="USD",
            fields=[
                ExtractedField(key="invoice_number", label="Invoice number", value="INV-1", raw_value="INV-1", data_type="identifier", evidence=Evidence(source_text="Invoice INV-1", page_number=1), confidence=0.98),
                ExtractedField(key="subtotal", label="Subtotal", value=100.0, raw_value="100.00", data_type="number", evidence=Evidence(source_text="Subtotal 100.00", page_number=1), confidence=0.98),
                ExtractedField(key="tax_amount", label="Tax", value=5.0, raw_value="5.00", data_type="number", evidence=Evidence(source_text="Tax 5.00", page_number=1), confidence=0.98),
                ExtractedField(key="discount", label="Discount", value=0.0, raw_value="0.00", data_type="number", evidence=Evidence(source_text="Discount 0.00", page_number=1), confidence=0.98),
                ExtractedField(key="total_amount", label="Total", value=105.0, raw_value="105.00", data_type="number", evidence=Evidence(source_text="Total 105.00", page_number=1), confidence=0.98),
            ],
            tables=[
                ExtractedTable(
                    name="line_items",
                    page_number=1,
                    columns=["Description", "Quantity", "Unit Price", "Amount"],
                    rows=[["Service", "1", "100.00", "100.00"]],
                )
            ],
        )


@pytest.fixture
def client():
    app.dependency_overrides[get_extraction_service] = lambda: StubExtractionService()
    with TestClient(app) as test_client:
        with SessionLocal() as session:
            session.execute(delete(DocumentRecord))
            session.commit()
        yield test_client
    app.dependency_overrides.clear()
