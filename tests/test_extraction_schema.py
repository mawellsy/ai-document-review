from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.extraction import InvoiceExtractionPayload


def valid_payload() -> dict:
    return {
        "invoice_number": "INV-1001",
        "invoice_date": "2026-09-01",
        "vendor_name": "Northwind Services",
        "vendor_address": "100 Main Street",
        "customer_name": "Contoso Ltd",
        "subtotal": 100.0,
        "tax": 5.0,
        "total": 105.0,
        "currency": "usd",
        "due_date": "2026-10-01",
        "line_items": [
            {
                "description": "Inspection",
                "quantity": 1,
                "unit_price": 100.0,
                "amount": 100.0,
            }
        ],
        "confidence": 0.95,
    }


def test_invoice_payload_parses_dates_and_normalizes_currency() -> None:
    payload = InvoiceExtractionPayload.model_validate(valid_payload())

    assert payload.invoice_date == date(2026, 9, 1)
    assert payload.currency == "USD"
    assert payload.line_items[0].description == "Inspection"


def test_invoice_payload_rejects_confidence_outside_range() -> None:
    data = valid_payload()
    data["confidence"] = 1.2

    with pytest.raises(ValidationError):
        InvoiceExtractionPayload.model_validate(data)


def test_invoice_payload_rejects_unexpected_fields() -> None:
    data = valid_payload()
    data["invented_field"] = "should fail"

    with pytest.raises(ValidationError):
        InvoiceExtractionPayload.model_validate(data)
