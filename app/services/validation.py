from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pycountry

from app.core.config import Settings
from app.schemas.extraction import InvoiceExtractionPayload


AUTO_ACCEPT_REQUIRED_FIELDS = (
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)

NON_TRANSACTION_CURRENCY_CODES = {"XTS", "XXX"}


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic reason an extraction requires human review."""

    code: str
    field: str | None
    message: str
    observed: Any = None
    expected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "observed": self.observed,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...]

    @property
    def review_required(self) -> bool:
        return bool(self.issues)


class InvoiceBusinessValidator:
    """Apply deterministic invoice checks after structurally valid AI extraction."""

    def __init__(self, settings: Settings) -> None:
        self.confidence_threshold = Decimal(str(settings.ai_confidence_threshold))
        self.amount_tolerance = Decimal(str(settings.amount_tolerance))

    def validate(self, payload: InvoiceExtractionPayload) -> ValidationResult:
        issues: list[ValidationIssue] = []

        self._validate_required_fields(payload, issues)
        self._validate_currency(payload, issues)
        self._validate_confidence(payload, issues)
        self._validate_dates(payload, issues)
        self._validate_totals(payload, issues)
        self._validate_line_items(payload, issues)

        return ValidationResult(issues=tuple(issues))

    def _validate_required_fields(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        for field_name in AUTO_ACCEPT_REQUIRED_FIELDS:
            value = getattr(payload, field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(
                    ValidationIssue(
                        code="required_field_missing",
                        field=field_name,
                        message=f"{field_name} is required for automatic acceptance.",
                    )
                )

        if not payload.line_items:
            issues.append(
                ValidationIssue(
                    code="line_items_missing",
                    field="line_items",
                    message="At least one line item is required for automatic acceptance.",
                )
            )

    def _validate_currency(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        if payload.currency is None:
            return

        currency = pycountry.currencies.get(alpha_3=payload.currency)
        if currency is None or payload.currency in NON_TRANSACTION_CURRENCY_CODES:
            issues.append(
                ValidationIssue(
                    code="invalid_currency",
                    field="currency",
                    message="Currency must be an assigned transactional ISO 4217 code.",
                    observed=payload.currency,
                    expected="ISO 4217 currency code",
                )
            )

    def _validate_confidence(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        confidence = Decimal(str(payload.confidence))
        if confidence < self.confidence_threshold:
            issues.append(
                ValidationIssue(
                    code="low_ai_confidence",
                    field="confidence",
                    message="AI confidence is below the automatic-acceptance threshold.",
                    observed=float(confidence),
                    expected=f">= {self.confidence_threshold}",
                )
            )

    def _validate_dates(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        # Pydantic already guarantees syntactically valid dates. Here we check chronology.
        if (
            payload.invoice_date is not None
            and payload.due_date is not None
            and payload.due_date < payload.invoice_date
        ):
            issues.append(
                ValidationIssue(
                    code="due_date_before_invoice_date",
                    field="due_date",
                    message="Due date cannot be earlier than invoice date.",
                    observed=payload.due_date.isoformat(),
                    expected=f">= {payload.invoice_date.isoformat()}",
                )
            )

    def _validate_totals(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        if payload.subtotal is None or payload.tax is None or payload.total is None:
            return

        subtotal = self._money(payload.subtotal)
        tax = self._money(payload.tax)
        total = self._money(payload.total)
        expected_total = subtotal + tax

        if not self._approximately_equal(expected_total, total):
            issues.append(
                ValidationIssue(
                    code="invoice_total_mismatch",
                    field="total",
                    message="Subtotal plus tax does not approximately equal total.",
                    observed=str(total),
                    expected=str(expected_total),
                )
            )

    def _validate_line_items(
        self,
        payload: InvoiceExtractionPayload,
        issues: list[ValidationIssue],
    ) -> None:
        if not payload.line_items:
            return

        line_total = Decimal("0")
        for index, item in enumerate(payload.line_items):
            quantity = Decimal(str(item.quantity))
            unit_price = self._money(item.unit_price)
            amount = self._money(item.amount)
            expected_amount = (quantity * unit_price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            line_total += amount

            if not self._approximately_equal(expected_amount, amount):
                issues.append(
                    ValidationIssue(
                        code="line_item_amount_mismatch",
                        field=f"line_items[{index}].amount",
                        message="Line-item quantity times unit price does not approximately equal amount.",
                        observed=str(amount),
                        expected=str(expected_amount),
                    )
                )

        if payload.subtotal is not None:
            subtotal = self._money(payload.subtotal)
            if not self._approximately_equal(line_total, subtotal):
                issues.append(
                    ValidationIssue(
                        code="line_items_subtotal_mismatch",
                        field="subtotal",
                        message="Line-item amounts do not approximately equal subtotal.",
                        observed=str(subtotal),
                        expected=str(line_total),
                    )
                )

    def _approximately_equal(self, left: Decimal, right: Decimal) -> bool:
        return abs(left - right) <= self.amount_tolerance

    @staticmethod
    def _money(value: float) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
