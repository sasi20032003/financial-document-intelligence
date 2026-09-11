from backend.app.schemas.document import DocumentType, ValidationStatus
from backend.app.schemas.extraction import ExtractedField, ExtractedTable, ExtractionResult
from backend.app.services.financial_validation_service import FinancialValidationService


def fields(values, period=None):
    return [
        ExtractedField(key=key, label=key, value=value, data_type="number", period=period)
        for key, value in values.items()
    ]


def test_invoice_total_and_line_items_pass():
    extraction = ExtractionResult(
        fields=fields({"subtotal": 100, "tax_amount": 5, "discount": 0, "total_amount": 105}),
        tables=[ExtractedTable(name="line_items", columns=["Description", "Quantity", "Unit Price", "Amount"], rows=[["A", "2", "50", "100"]])],
    )
    result = FinancialValidationService().validate(DocumentType.invoice, extraction)
    assert result.overall_status == ValidationStatus.PASS
    assert all(check.status == ValidationStatus.PASS for check in result.checks)


def test_invoice_variance_fails():
    extraction = ExtractionResult(
        fields=fields({"subtotal": 100, "tax_amount": 5, "discount": 0, "total_amount": 110})
    )
    result = FinancialValidationService(tolerance=0.001).validate(DocumentType.invoice, extraction)
    assert result.overall_status == ValidationStatus.FAIL
    assert result.checks[0].variance == -5


def test_missing_financial_fields_are_not_applicable():
    extraction = ExtractionResult(fields=fields({"total_assets": 100}, period="2026"))
    result = FinancialValidationService().validate(DocumentType.balance_sheet, extraction)
    assert result.overall_status == ValidationStatus.NOT_APPLICABLE
    assert result.checks[0].status == ValidationStatus.NOT_APPLICABLE
    assert "total_capital_and_liabilities" in result.checks[0].notes


def test_balance_sheet_validates_each_period():
    extraction = ExtractionResult(
        fields=fields({"total_assets": 500, "total_capital_and_liabilities": 500}, "2026")
        + fields({"total_assets": 450, "total_capital_and_liabilities": 440}, "2025")
    )
    result = FinancialValidationService(tolerance=0.001).validate(DocumentType.balance_sheet, extraction)
    statuses = {check.period: check.status for check in result.checks}
    assert statuses == {"2026": ValidationStatus.PASS, "2025": ValidationStatus.FAIL}


def test_parentheses_are_negative():
    assert FinancialValidationService._decimal("(1,250.50)") == -1250.5
    assert FinancialValidationService._decimal("[25]") == -25
