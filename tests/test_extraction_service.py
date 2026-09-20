from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models.document import Document
from app.schemas.extraction import InvoiceExtractionPayload
from app.services.extraction import AIExtractionError, InvoiceExtractor


class FakeResponses:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, results: list[object]) -> None:
        self.responses = FakeResponses(results)


def payload() -> InvoiceExtractionPayload:
    return InvoiceExtractionPayload.model_validate(
        {
            "invoice_number": "INV-1001",
            "invoice_date": "2026-09-01",
            "vendor_name": "Northwind Services",
            "vendor_address": None,
            "customer_name": "Contoso Ltd",
            "subtotal": 100,
            "tax": 5,
            "total": 105,
            "currency": "USD",
            "due_date": "2026-10-01",
            "line_items": [],
            "confidence": 0.94,
        }
    )


def make_document(tmp_path: Path, content_type: str = "image/png") -> Document:
    suffix = ".pdf" if content_type == "application/pdf" else ".png"
    path = tmp_path / f"invoice{suffix}"
    path.write_bytes(b"document-bytes")
    return Document(
        id="doc-1",
        original_filename=f"invoice{suffix}",
        stored_filename=f"doc-1{suffix}",
        content_type=content_type,
        file_size_bytes=path.stat().st_size,
        storage_path=str(path),
        processing_status="uploaded",
    )


def test_extractor_uses_structured_output_and_image_input(tmp_path: Path) -> None:
    response = SimpleNamespace(id="resp-1", output_parsed=payload())
    client = FakeClient([response])
    settings = Settings(_env_file=None, ai_model="test-model", ai_max_attempts=2)
    extractor = InvoiceExtractor(settings, client=client)

    result = extractor.extract(make_document(tmp_path))

    assert result.payload.invoice_number == "INV-1001"
    assert result.provider_response_id == "resp-1"
    call = client.responses.calls[0]
    assert call["text_format"] is InvoiceExtractionPayload
    assert call["input"][0]["content"][0]["type"] == "input_image"


def test_extractor_uses_file_input_for_pdf(tmp_path: Path) -> None:
    response = SimpleNamespace(id="resp-2", output_parsed=payload())
    client = FakeClient([response])
    settings = Settings(_env_file=None, ai_model="test-model")

    InvoiceExtractor(settings, client=client).extract(make_document(tmp_path, "application/pdf"))

    content = client.responses.calls[0]["input"][0]["content"]
    assert content[0]["type"] == "input_file"
    assert content[0]["file_data"].startswith("data:application/pdf;base64,")


def test_extractor_retries_transient_failure(tmp_path: Path) -> None:
    response = SimpleNamespace(id="resp-3", output_parsed=payload())
    client = FakeClient([RuntimeError("temporary provider error"), response])
    settings = Settings(_env_file=None, ai_model="test-model", ai_max_attempts=2)

    result = InvoiceExtractor(settings, client=client).extract(make_document(tmp_path))

    assert result.payload.total == 105
    assert len(client.responses.calls) == 2


def test_extractor_raises_after_retry_limit(tmp_path: Path) -> None:
    client = FakeClient([RuntimeError("failure 1"), RuntimeError("failure 2")])
    settings = Settings(_env_file=None, ai_model="test-model", ai_max_attempts=2)

    with pytest.raises(AIExtractionError, match="2 attempts"):
        InvoiceExtractor(settings, client=client).extract(make_document(tmp_path))
