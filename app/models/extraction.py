from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.line_item import LineItem


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    invoice_number: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    vendor_address: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(String(255))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    due_date: Mapped[date | None] = mapped_column(Date)

    model_used: Mapped[str] = mapped_column(String(150), nullable=False)
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    raw_response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_errors_json: Mapped[list[dict] | None] = mapped_column(JSON)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="extractions")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan"
    )
