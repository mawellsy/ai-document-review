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
from app.services.extraction import AIExtractionResult


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-image-content"


class ReviewRequiredExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-REVIEW-001",
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
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="review-1")


class LowConfidenceExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-REVIEW-002",
                "invoice_date": "2026-09-01",
                "vendor_name": "Northwind Services",
                "vendor_address": "100 Main Street",
                "customer_name": "Contoso Ltd",
                "subtotal": 200,
                "tax": 10,
                "total": 210,
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
                "confidence": 0.40,
            }
        )
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="review-2")


class ValidExtractor:
    def extract(self, document) -> AIExtractionResult:
        payload = InvoiceExtractionPayload.model_validate(
            {
                "invoice_number": "INV-VALID-001",
                "invoice_date": "2026-09-01",
                "vendor_name": "Northwind Services",
                "vendor_address": "100 Main Street",
                "customer_name": "Contoso Ltd",
                "subtotal": 200,
                "tax": 10,
                "total": 210,
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
        return AIExtractionResult(payload=payload, model_used="mock-model", provider_response_id="valid-1")


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
    app.dependency_overrides[get_invoice_extractor] = lambda: ReviewRequiredExtractor()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def upload_and_extract(client: TestClient) -> str:
    upload = client.post(
        "/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    extraction = client.post(f"/documents/{document_id}/extractions")
    assert extraction.status_code == 201
    return document_id


def test_review_required_extraction_enters_pending_queue(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.get("/reviews")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["document_id"] == document_id
    assert body[0]["review_status"] == "pending"
    assert body[0]["invoice_number"] == "INV-REVIEW-001"
    assert {issue["code"] for issue in body[0]["validation_errors"]} == {
        "invoice_total_mismatch"
    }


def test_review_detail_preserves_original_candidate_and_reasons(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.get(f"/reviews/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["original_extraction"]["total"] == "999.00"
    assert body["original_extraction"]["review_required"] is True
    assert body["authoritative_result"]["total"] == "999.00"
    assert body["authoritative_result"]["field_sources"]["total"] == "ai"
    assert "invoice_total_mismatch" in body["reason"]
    assert body["corrections"] is None


def test_human_correction_becomes_authoritative_without_mutating_ai_record(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.post(
        f"/reviews/{document_id}",
        json={
            "corrected_by": "reviewer@example.com",
            "corrections": {"total": 210},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "completed"
    assert body["corrected_by"] == "reviewer@example.com"
    assert body["corrections"] == {"total": 210.0}
    assert body["original_extraction"]["total"] == "999.00"
    assert body["authoritative_result"]["total"] == "210.00"
    assert body["authoritative_result"]["field_sources"]["total"] == "human"
    assert body["authoritative_result"]["field_sources"]["vendor_name"] == "ai"

    document = client.get(f"/documents/{document_id}")
    assert document.json()["processing_status"] == "reviewed"

    pending = client.get("/reviews")
    assert pending.json() == []

    completed = client.get("/reviews?status=completed")
    assert len(completed.json()) == 1


def test_completed_review_persists_across_followup_get(client: TestClient) -> None:
    document_id = upload_and_extract(client)
    client.post(
        f"/reviews/{document_id}",
        json={
            "corrected_by": "Miguel",
            "corrections": {"total": 210, "currency": "usd"},
        },
    )

    response = client.get(f"/reviews/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "completed"
    assert body["corrections"] == {"total": 210.0, "currency": "USD"}
    assert body["authoritative_result"]["currency"] == "USD"
    assert body["authoritative_result"]["field_sources"]["currency"] == "human"
    assert body["corrected_at"] is not None


def test_invalid_human_correction_stays_pending(client: TestClient) -> None:
    document_id = upload_and_extract(client)

    response = client.post(
        f"/reviews/{document_id}",
        json={
            "corrected_by": "Miguel",
            "corrections": {"total": 500},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["validation_errors"][0]["code"] == "invoice_total_mismatch"

    detail = client.get(f"/reviews/{document_id}").json()
    assert detail["review_status"] == "pending"
    assert detail["corrections"] is None


def test_low_confidence_invoice_can_be_human_confirmed_without_data_changes(client: TestClient) -> None:
    app.dependency_overrides[get_invoice_extractor] = lambda: LowConfidenceExtractor()
    document_id = upload_and_extract(client)

    response = client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Miguel", "corrections": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "completed"
    assert body["corrections"] == {}
    assert set(body["authoritative_result"]["field_sources"].values()) == {"ai"}


def test_submit_review_requires_pending_review(client: TestClient) -> None:
    app.dependency_overrides[get_invoice_extractor] = lambda: ValidExtractor()
    document_id = upload_and_extract(client)

    response = client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Miguel", "corrections": {}},
    )

    assert response.status_code == 404


def test_completed_review_cannot_be_submitted_twice(client: TestClient) -> None:
    document_id = upload_and_extract(client)
    first = client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Miguel", "corrections": {"total": 210}},
    )
    assert first.status_code == 200

    second = client.post(
        f"/reviews/{document_id}",
        json={"corrected_by": "Another Reviewer", "corrections": {"total": 210}},
    )

    assert second.status_code == 409
