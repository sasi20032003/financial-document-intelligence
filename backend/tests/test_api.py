from backend.tests.conftest import pdf_bytes
from backend.app.core.config import Settings, get_settings
from backend.app.main import app



def test_api_base_endpoint(client):
    response = client.get("/api/v1")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["health"] == "/api/v1/health"

    slash_response = client.get("/api/v1/")
    assert slash_response.status_code == 200
    assert slash_response.json() == response.json()


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_process_list_and_get_flow(client):
    response = client.post(
        "/api/v1/documents/process",
        data={"document_type": "invoice"},
        files={"file": ("api-flow.pdf", pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["document_name"] == "api-flow.pdf"
    assert payload["processing_status"] == "PASS"
    assert payload["validation"]["overall_status"] == "PASS"
    assert payload["file_validation"]["page_count"] == 1

    listing = client.get("/api/v1/documents").json()
    assert listing["total"] == 1
    assert listing["items"][0]["document_name"] == "api-flow.pdf"

    stored = client.get("/api/v1/documents/api-flow.pdf")
    assert stored.status_code == 200
    assert stored.json() == payload


def test_api_returns_consistent_error_envelope(client):
    response = client.post(
        "/api/v1/documents/process",
        data={"document_type": "invoice"},
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_get_unknown_document(client):
    response = client.get("/api/v1/documents/missing.pdf")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

def test_all_four_document_types_are_accepted(client):
    types = ["invoice", "balance_sheet", "profit_and_loss", "cash_flow_statement"]
    for document_type in types:
        response = client.post(
            "/api/v1/documents/process",
            data={"document_type": document_type},
            files={"file": (document_type + ".pdf", pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201
        assert response.json()["document_type"] == document_type


def test_dataset_manifest_and_processing(client, tmp_path):
    balance_sheets = tmp_path / "Balance Sheet"
    balance_sheets.mkdir()
    source = balance_sheets / "statement-2026.pdf"
    source.write_bytes(pdf_bytes())
    (balance_sheets / "ignore.txt").write_text("unsupported")
    app.dependency_overrides[get_settings] = lambda: Settings(
        dataset_directory=tmp_path
    )

    manifest_response = client.get("/api/v1/dataset")

    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["available"] is True
    assert manifest["total"] == 1
    assert manifest["remaining"] == 1
    assert manifest["items"][0]["relative_path"] == "Balance Sheet/statement-2026.pdf"
    assert manifest["items"][0]["document_type"] == "balance_sheet"

    process_response = client.post(
        "/api/v1/dataset/process",
        json={"relative_path": manifest["items"][0]["relative_path"]},
    )

    assert process_response.status_code == 201
    assert process_response.json()["document_name"] == "statement-2026.pdf"
    assert process_response.json()["document_type"] == "balance_sheet"
    refreshed = client.get("/api/v1/dataset").json()
    assert refreshed["processed"] == 1
    assert refreshed["remaining"] == 0


def test_dataset_processing_rejects_path_traversal(client, tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(
        dataset_directory=tmp_path
    )
    response = client.post(
        "/api/v1/dataset/process",
        json={"relative_path": "../outside.pdf"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DATASET_PATH"
