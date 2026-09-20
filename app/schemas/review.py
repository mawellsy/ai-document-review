from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.extraction import (
    ExtractionResponse,
    InvoiceLineItemPayload,
    ValidationIssueResponse,
)


class InvoiceCorrectionPayload(BaseModel):
    """Partial human corrections applied over the immutable AI extraction."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_date: date | None = None
    vendor_name: str | None = Field(default=None, max_length=255)
    vendor_address: str | None = Field(default=None, max_length=2000)
    customer_name: str | None = Field(default=None, max_length=255)
    subtotal: float | None = Field(default=None, ge=0)
    tax: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_date: date | None = None
    line_items: list[InvoiceLineItemPayload] | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class ReviewSubmission(BaseModel):
    """Human decision for one review-required document.

    An empty corrections object means the reviewer confirms the AI values as-is.
    """

    model_config = ConfigDict(extra="forbid")

    corrected_by: str = Field(min_length=1, max_length=150)
    corrections: InvoiceCorrectionPayload = Field(default_factory=InvoiceCorrectionPayload)


class AuthoritativeLineItemResponse(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class AuthoritativeInvoiceResponse(BaseModel):
    invoice_number: str | None
    invoice_date: date | None
    vendor_name: str | None
    vendor_address: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None
    due_date: date | None
    line_items: list[AuthoritativeLineItemResponse]
    field_sources: dict[str, Literal["ai", "human"]]


class ReviewQueueItemResponse(BaseModel):
    review_id: str
    document_id: str
    original_filename: str
    review_status: str
    reason: str
    created_at: datetime
    invoice_number: str | None
    vendor_name: str | None
    total: Decimal | None
    currency: str | None
    ai_confidence: Decimal | None
    validation_errors: list[ValidationIssueResponse]


class ReviewDetailResponse(BaseModel):
    review_id: str
    document_id: str
    original_filename: str
    review_status: str
    reason: str
    created_at: datetime
    corrected_by: str | None
    corrected_at: datetime | None
    corrections: dict[str, Any] | None
    original_extraction: ExtractionResponse
    authoritative_result: AuthoritativeInvoiceResponse
