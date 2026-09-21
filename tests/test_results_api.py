from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.extractions import get_invoice_extractor
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.schemas.extraction import InvoiceExtractionPayload
from app.services.extraction import AIExtractionResult


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-image-content"


class ValidTwoLineExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-EXPORT-001",
                "invoice_date": "2026-09-01",
                "vendor_name": "Northwind Services",
                "vendor_address": "100 Main Street",
                "customer_name": "Contoso Ltd",
                "subtotal": 250,
                "tax": 25,
                "total": 275,
                "currency": "USD",
                "due_date": "2026-10-01",
                "line_items": [
                    {
                        "description": "Inspection",
                        "quantity": 1,
                        "unit_price": 50,
                        "amount": 50,
                    },
                    {
                        "description": "Preventive maintenance",
                        "quantity": 2,
                        "unit_price": 100,
                        "amount": 200,
                    },
                ],
                "confidence": 0.97,
            }
        )
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="export-1")


class ReviewRequiredExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-EXPORT-002",
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
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="export-2")


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
        ai_confidence_threshold=0.80,
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_invoice_extractor] = lambda: ValidTwoLineExtractor()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def upload(client: TestClient, filename: str = "invoice export.png") -> str:
    response = client.post(
        "/documents",
        files={"file": (filename, PNG_BYTES, "image/png")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload_and_extract(client: TestClient, filename: str = "invoice export.png") -> str:
    document_id = upload(client, filename)
    response = client.post(f"/documents/{document_id}/extractions")
    assert response.status_code == 201
    return document_id


def test_result_endpoint_returns_validated_ai_result(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.get(f"/documents/{document_id}/result")

    assert response.status_code == 200
    body = response.json()
    assert body["processing_status"] == "validated"
    assert body["result_source"] == "ai_validated"
    assert body["reviewed_by"] is None
    assert body["authoritative_result"]["total"] == "275.00"
    assert set(body["authoritative_result"]["field_sources"].values()) == {"ai"}


def test_result_endpoint_waits_for_required_human_review(client: TestClient) -> None:
    app.dependency_overrides[get_invoice_extractor] = lambda: ReviewRequiredExtractor()
    document_id = upload_and_extract(client)

    response = client.get(f"/documents/{document_id}/result")

    assert response.status_code == 409
    assert response.json()["detail"] == "Document is awaiting human review."


def test_reviewed_result_uses_human_correction_and_provenance(client: TestClient) -> None:
    app.dependency_overrides[get_invoice_extractor] = lambda: ReviewRequiredExtractor()
    document_id = upload_and_extract(client)
    review = client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Miguel", "corrections": {"total": 210}},
    )
    assert review.status_code == 200

    response = client.get(f"/documents/{document_id}/result")

    assert response.status_code == 200
    body = response.json()
    assert body["processing_status"] == "reviewed"
    assert body["result_source"] == "human_reviewed"
    assert body["reviewed_by"] == "Miguel"
    assert body["reviewed_at"] is not None
    assert body["authoritative_result"]["total"] == "210.00"
    assert body["authoritative_result"]["field_sources"]["total"] == "human"
    assert body["authoritative_result"]["field_sources"]["vendor_name"] == "ai"


def test_json_export_downloads_authoritative_result(client: TestClient) -> None:
    document_id = upload_and_extract(client, filename="September Invoice.png")

    response = client.get(f"/documents/{document_id}/exports/json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == 'attachment; filename="September-Invoice-result.json"'
    body = response.json()
    assert body["document_id"] == document_id
    assert body["authoritative_result"]["invoice_number"] == "INV-EXPORT-001"
    assert body["authoritative_result"]["line_items"][1]["description"] == "Preventive maintenance"


def test_csv_export_emits_one_row_per_line_item(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.get(f"/documents/{document_id}/exports/csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert rows[0]["document_id"] == document_id
    assert rows[0]["invoice_number"] == "INV-EXPORT-001"
    assert rows[0]["line_item_number"] == "1"
    assert rows[1]["line_item_number"] == "2"
    assert rows[1]["line_item_description"] == "Preventive maintenance"
    assert rows[1]["total"] == "275.00"


def test_csv_export_preserves_human_review_provenance(client: TestClient) -> None:
    app.dependency_overrides[get_invoice_extractor] = lambda: ReviewRequiredExtractor()
    document_id = upload_and_extract(client)
    client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Miguel", "corrections": {"total": 210}},
    )

    response = client.get(f"/documents/{document_id}/exports/csv")

    assert response.status_code == 200
    row = next(csv.DictReader(io.StringIO(response.text)))
    assert row["result_source"] == "human_reviewed"
    assert row["reviewed_by"] == "Miguel"
    assert row["total"] == "210.00"
    field_sources = json.loads(row["field_sources_json"])
    assert field_sources["total"] == "human"
    assert field_sources["currency"] == "ai"


def test_result_returns_404_for_unknown_document(client: TestClient) -> None:
    response = client.get("/documents/not-a-document/result")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_export_returns_409_before_extraction(client: TestClient) -> None:
    document_id = upload(client)

    response = client.get(f"/documents/{document_id}/exports/json")

    assert response.status_code == 409
    assert "uploaded" in response.json()["detail"]
