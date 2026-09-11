from io import BytesIO

import pytest
from PIL import Image

from backend.app.core.config import Settings
from backend.app.core.exceptions import DocumentInputError
from backend.app.services.document_validation_service import DocumentValidationService
from backend.tests.conftest import pdf_bytes


@pytest.fixture
def validator():
    return DocumentValidationService(Settings(max_pages=3, max_file_size_bytes=1024 * 1024))


def test_accepts_valid_pdf(validator):
    result = validator.validate("statement.pdf", "application/pdf", pdf_bytes())
    assert result.page_count == 1
    assert result.validation.status == "PASS"


def test_rejects_unsupported_type(validator):
    with pytest.raises(DocumentInputError) as error:
        validator.validate("notes.txt", "text/plain", b"hello")
    assert error.value.code == "UNSUPPORTED_FILE_TYPE"
    assert error.value.status_code == 415


def test_rejects_corrupted_pdf(validator):
    with pytest.raises(DocumentInputError) as error:
        validator.validate("broken.pdf", "application/pdf", b"%PDF-not-a-pdf")
    assert error.value.code == "CORRUPTED_PDF"


def test_rejects_more_than_three_pages(validator):
    with pytest.raises(DocumentInputError) as error:
        validator.validate("long.pdf", "application/pdf", pdf_bytes(4))
    assert error.value.code == "PAGE_LIMIT_EXCEEDED"


def test_accepts_valid_png(validator):
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    result = validator.validate("scan.png", "image/png", stream.getvalue())
    assert result.mime_type == "image/png"
    assert result.page_count == 1


def test_rejects_extension_signature_mismatch(validator):
    stream = BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    with pytest.raises(DocumentInputError) as error:
        validator.validate("scan.jpg", "image/jpeg", stream.getvalue())
    assert error.value.code == "FILE_TYPE_MISMATCH"
