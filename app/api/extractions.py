from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.line_item import LineItem
from app.schemas.extraction import ExtractionResponse
from app.services.extraction import (
    AIConfigurationError,
    AIExtractionError,
    InvoiceExtractor,
)

router = APIRouter(prefix="/documents", tags=["extractions"])


def get_invoice_extractor(settings: Settings = Depends(get_settings)) -> InvoiceExtractor:
    return InvoiceExtractor(settings=settings)


def _decimal_or_none(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


@router.post(
    "/{document_id}/extractions",
    response_model=ExtractionResponse,
    status_code=status.HTTP_201_CREATED,
)
def extract_document(
    document_id: str,
    db: Session = Depends(get_db),
    extractor: InvoiceExtractor = Depends(get_invoice_extractor),
) -> Extraction:
    """Run AI extraction for one uploaded document and persist the typed result."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    document.processing_status = "extracting"
    db.commit()

    try:
        result = extractor.extract(document)
    except AIConfigurationError as exc:
        document.processing_status = "extraction_failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIExtractionError as exc:
        document.processing_status = "extraction_failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    payload = result.payload
    extraction = Extraction(
        document_id=document.id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        vendor_name=payload.vendor_name,
        vendor_address=payload.vendor_address,
        customer_name=payload.customer_name,
        subtotal=_decimal_or_none(payload.subtotal),
        tax=_decimal_or_none(payload.tax),
        total=_decimal_or_none(payload.total),
        currency=payload.currency,
        due_date=payload.due_date,
        model_used=result.model_used,
        ai_confidence=Decimal(str(payload.confidence)),
        raw_response_json=payload.model_dump(mode="json"),
        validation_errors_json=None,
        review_required=False,
        line_items=[
            LineItem(
                description=item.description,
                quantity=Decimal(str(item.quantity)),
                unit_price=Decimal(str(item.unit_price)),
                amount=Decimal(str(item.amount)),
            )
            for item in payload.line_items
        ],
    )

    try:
        db.add(extraction)
        document.processing_status = "extracted"
        db.commit()
        db.refresh(extraction)
    except SQLAlchemyError as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.processing_status = "extraction_failed"
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The extraction could not be persisted.",
        ) from exc

    return _load_extraction(db, extraction.id)


@router.get("/{document_id}/extractions/latest", response_model=ExtractionResponse)
def get_latest_extraction(document_id: str, db: Session = Depends(get_db)) -> Extraction:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    statement = (
        select(Extraction)
        .where(Extraction.document_id == document_id)
        .options(selectinload(Extraction.line_items))
        .order_by(Extraction.created_at.desc())
        .limit(1)
    )
    extraction = db.scalar(statement)
    if extraction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No extraction found.")
    return extraction


def _load_extraction(db: Session, extraction_id: str) -> Extraction:
    statement = (
        select(Extraction)
        .where(Extraction.id == extraction_id)
        .options(selectinload(Extraction.line_items))
    )
    extraction = db.scalar(statement)
    if extraction is None:
        raise RuntimeError("Extraction disappeared after persistence.")
    return extraction
