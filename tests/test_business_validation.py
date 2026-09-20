from copy import deepcopy

from app.core.config import Settings
from app.schemas.extraction import InvoiceExtractionPayload
from app.services.validation import InvoiceBusinessValidator


def valid_data() -> dict:
    return {
        "invoice_number": "INV-1001",
        "invoice_date": "2026-09-01",
        "vendor_name": "Northwind Services",
        "vendor_address": "100 Main Street",
        "customer_name": "Contoso Ltd",
        "subtotal": 200.00,
        "tax": 10.00,
        "total": 210.00,
        "currency": "USD",
        "due_date": "2026-10-01",
        "line_items": [
            {
                "description": "Preventive maintenance",
                "quantity": 2,
                "unit_price": 100.00,
                "amount": 200.00,
            }
        ],
        "confidence": 0.97,
    }


def validate(data: dict, **settings_overrides):
    settings = Settings(_env_file=None, **settings_overrides)
    payload = InvoiceExtractionPayload.model_validate(data)
    return InvoiceBusinessValidator(settings).validate(payload)


def issue_codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_consistent_invoice_passes_business_validation() -> None:
    result = validate(valid_data())

    assert result.review_required is False
    assert result.issues == ()


def test_missing_required_field_routes_to_review() -> None:
    data = valid_data()
    data["invoice_number"] = None

    result = validate(data)

    assert result.review_required is True
    assert "required_field_missing" in issue_codes(result)


def test_invalid_iso_currency_routes_to_review() -> None:
    data = valid_data()
    data["currency"] = "ZZZ"

    result = validate(data)

    assert "invalid_currency" in issue_codes(result)


def test_low_confidence_routes_to_review() -> None:
    data = valid_data()
    data["confidence"] = 0.79

    result = validate(data, ai_confidence_threshold=0.80)

    assert "low_ai_confidence" in issue_codes(result)


def test_invoice_total_mismatch_routes_to_review() -> None:
    data = valid_data()
    data["total"] = 250.00

    result = validate(data)

    assert "invoice_total_mismatch" in issue_codes(result)


def test_line_item_sum_mismatch_routes_to_review() -> None:
    data = valid_data()
    data["line_items"][0]["amount"] = 190.00
    data["line_items"][0]["unit_price"] = 95.00

    result = validate(data)

    assert "line_items_subtotal_mismatch" in issue_codes(result)


def test_line_item_quantity_price_mismatch_routes_to_review() -> None:
    data = valid_data()
    data["line_items"][0]["amount"] = 200.00
    data["line_items"][0]["unit_price"] = 90.00

    result = validate(data)

    assert "line_item_amount_mismatch" in issue_codes(result)


def test_due_date_before_invoice_date_routes_to_review() -> None:
    data = valid_data()
    data["due_date"] = "2026-08-31"

    result = validate(data)

    assert "due_date_before_invoice_date" in issue_codes(result)


def test_tolerance_allows_one_cent_rounding_difference() -> None:
    data = deepcopy(valid_data())
    data["tax"] = 10.001
    data["total"] = 210.01

    result = validate(data, amount_tolerance=0.01)

    assert "invoice_total_mismatch" not in issue_codes(result)
