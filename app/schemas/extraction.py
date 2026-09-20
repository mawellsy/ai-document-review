from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceLineItemPayload(BaseModel):
    """One line item exactly as extracted from the source document."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=1000)
    quantity: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    amount: float = Field(ge=0)


class InvoiceExtractionPayload(BaseModel):
    """Strict structured output expected from the AI provider."""

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
    line_items: list[InvoiceLineItemPayload] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class LineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
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
    model_used: str
    ai_confidence: Decimal | None
    review_required: bool
    created_at: datetime
    line_items: list[LineItemResponse]
