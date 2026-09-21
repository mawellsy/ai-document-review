from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.review import Review
from app.schemas.review import AuthoritativeInvoiceResponse, AuthoritativeLineItemResponse


class DocumentResultNotFoundError(Exception):
    """Raised when the requested document does not exist."""


class DocumentResultNotReadyError(Exception):
    """Raised when a document exists but does not yet have an exportable final result."""


@dataclass(frozen=True)
class ResolvedDocumentResult:
    document: Document
    extraction: Extraction
    review: Review | None
    authoritative_result: AuthoritativeInvoiceResponse
    result_source: Literal["ai_validated", "human_reviewed"]


def resolve_document_result(db: Session, document_id: str) -> ResolvedDocumentResult:
    """Resolve the final downstream-facing invoice record for one document.

    Only validated AI results and completed human-reviewed results are exportable.
    Pending-review and incomplete processing states intentionally fail closed.
    """
    statement = (
        select(Document)
        .where(Document.id == document_id)
        .options(
            selectinload(Document.extractions).selectinload(Extraction.line_items),
            selectinload(Document.reviews),
        )
    )
    document = db.scalar(statement)
    if document is None:
        raise DocumentResultNotFoundError(document_id)

    extraction = latest_extraction(document)
    if extraction is None:
        raise DocumentResultNotReadyError(
            f"Document result is not ready. Current status: {document.processing_status}."
        )

    if document.processing_status == "validated":
        return ResolvedDocumentResult(
            document=document,
            extraction=extraction,
            review=None,
            authoritative_result=build_authoritative_result(extraction, {}),
            result_source="ai_validated",
        )

    if document.processing_status == "reviewed":
        review = latest_completed_review(document)
        if review is None:
            raise DocumentResultNotReadyError(
                "Document is marked reviewed but has no completed review record."
            )
        corrections = review.corrected_values_json or {}
        return ResolvedDocumentResult(
            document=document,
            extraction=extraction,
            review=review,
            authoritative_result=build_authoritative_result(extraction, corrections),
            result_source="human_reviewed",
        )

    if document.processing_status == "review_required":
        raise DocumentResultNotReadyError("Document is awaiting human review.")

    raise DocumentResultNotReadyError(
        f"Document result is not ready. Current status: {document.processing_status}."
    )


def latest_extraction(document: Document) -> Extraction | None:
    if not document.extractions:
        return None
    return max(document.extractions, key=lambda extraction: extraction.created_at)


def latest_completed_review(document: Document) -> Review | None:
    completed = [review for review in document.reviews if review.review_status == "completed"]
    if not completed:
        return None
    return max(completed, key=lambda review: review.created_at)


def payload_dict_from_extraction(extraction: Extraction) -> dict:
    return {
        "invoice_number": extraction.invoice_number,
        "invoice_date": extraction.invoice_date,
        "vendor_name": extraction.vendor_name,
        "vendor_address": extraction.vendor_address,
        "customer_name": extraction.customer_name,
        "subtotal": float(extraction.subtotal) if extraction.subtotal is not None else None,
        "tax": float(extraction.tax) if extraction.tax is not None else None,
        "total": float(extraction.total) if extraction.total is not None else None,
        "currency": extraction.currency,
        "due_date": extraction.due_date,
        "line_items": [
            {
                "description": item.description,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "amount": float(item.amount),
            }
            for item in extraction.line_items
        ],
        "confidence": float(extraction.ai_confidence or Decimal("0")),
    }


def build_authoritative_result(
    extraction: Extraction,
    corrections: dict,
) -> AuthoritativeInvoiceResponse:
    """Overlay human corrections on the immutable AI extraction."""
    original = payload_dict_from_extraction(extraction)
    merged = {**original, **corrections}
    fields = (
        "invoice_number",
        "invoice_date",
        "vendor_name",
        "vendor_address",
        "customer_name",
        "subtotal",
        "tax",
        "total",
        "currency",
        "due_date",
        "line_items",
    )
    sources = {field: ("human" if field in corrections else "ai") for field in fields}

    line_items = [
        AuthoritativeLineItemResponse(
            description=item["description"],
            quantity=Decimal(str(item["quantity"])),
            unit_price=Decimal(str(item["unit_price"])).quantize(Decimal("0.01")),
            amount=Decimal(str(item["amount"])).quantize(Decimal("0.01")),
        )
        for item in merged["line_items"]
    ]

    def money(name: str) -> Decimal | None:
        value = merged[name]
        return Decimal(str(value)).quantize(Decimal("0.01")) if value is not None else None

    return AuthoritativeInvoiceResponse(
        invoice_number=merged["invoice_number"],
        invoice_date=merged["invoice_date"],
        vendor_name=merged["vendor_name"],
        vendor_address=merged["vendor_address"],
        customer_name=merged["customer_name"],
        subtotal=money("subtotal"),
        tax=money("tax"),
        total=money("total"),
        currency=merged["currency"],
        due_date=merged["due_date"],
        line_items=line_items,
        field_sources=sources,
    )
