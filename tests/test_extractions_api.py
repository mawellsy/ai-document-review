from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401
from app.api.extractions import get_invoice_extractor
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.schemas.extraction import InvoiceExtractionPayload
from app.services.extraction import AIExtractionError, AIExtractionResult


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-image-content"


class SuccessfulExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-09-01",
                "vendor_name": "Northwind Services",
                "vendor_address": "100 Main Street",
                "customer_name": "Contoso Ltd",
                "subtotal": 200,
                "tax": 10,
                "total": 210,
                "currency": "usd",
                "due_date": "2026-10-01",
                "line_items": [
                    {
                        "description": "Preventive maintenance",
                        "quantity": 2,
                        "unit_price": 100,
                        "amount": 200,
                    }
                ],
                "confidence": 0.97,
            }
        )
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="mock-1")


class InconsistentExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-2026-002",
                "invoice_date": "2026-09-01",
                "vendor_name": "Northwind Services",
                "vendor_address": "100 Main Street",
                "customer_name": "Contoso Ltd",
                "subtotal": 200,
                "tax": 10,
                "total": 999,
                "currency": "USD",
                "due_date": "2026-10-01",
                "line_items": [
                    {
                        "description": "Preventive maintenance",
                        "quantity": 2,
                        "unit_price": 100,
                        "amount": 200,
                    }
                ],
                "confidence": 0.97,
            }
        )
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="mock-2")


class FailingExtractor:
    def extract(self, document) -> AIExtractionResult:
        raise AIExtractionError("Mock extraction failure.")


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        upload_dir=tmp_path / "uploads",
        max_upload_mb=1,
        ai_model="mock-model",
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_invoice_extractor] = lambda: SuccessfulExtractor()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def upload_document(client: TestClient) -> str:
    response = client.post(
        "/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_extract_document_persists_structured_result(client: TestClient) -> None:
    document_id = upload_document(client)

    response = client.post(f"/documents/{document_id}/extractions")

    assert response.status_code == 201
    body = response.json()
    assert body["document_id"] == document_id
    assert body["invoice_number"] == "INV-2026-001"
    assert body["currency"] == "USD"
    assert body["model_used"] == "mock-model"
    assert body["review_required"] is False
    assert body["validation_errors"] == []
    assert body["line_items"][0]["description"] == "Preventive maintenance"

    latest = client.get(f"/documents/{document_id}/extractions/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    document = client.get(f"/documents/{document_id}")
    assert document.json()["processing_status"] == "validated"


def test_business_validation_routes_inconsistent_invoice_to_review(client: TestClient) -> None:
    document_id = upload_document(client)
    app.dependency_overrides[get_invoice_extractor] = lambda: InconsistentExtractor()

    response = client.post(f"/documents/{document_id}/extractions")

    assert response.status_code == 201
    body = response.json()
    assert body["review_required"] is True
    assert {issue["code"] for issue in body["validation_errors"]} == {"invoice_total_mismatch"}

    document = client.get(f"/documents/{document_id}")
    assert document.json()["processing_status"] == "review_required"


def test_extraction_failure_marks_document_failed(client: TestClient) -> None:
    document_id = upload_document(client)
    app.dependency_overrides[get_invoice_extractor] = lambda: FailingExtractor()

    response = client.post(f"/documents/{document_id}/extractions")

    assert response.status_code == 502
    document = client.get(f"/documents/{document_id}")
    assert document.json()["processing_status"] == "extraction_failed"


def test_latest_extraction_returns_404_when_none_exists(client: TestClient) -> None:
    document_id = upload_document(client)

    response = client.get(f"/documents/{document_id}/extractions/latest")

    assert response.status_code == 404
