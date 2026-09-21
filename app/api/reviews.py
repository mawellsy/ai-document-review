from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.extractions import get_invoice_validator
from app.db.session import get_db
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.review import Review
from app.schemas.extraction import ExtractionResponse, InvoiceExtractionPayload
from app.schemas.review import (
    ReviewDetailResponse,
    ReviewQueueItemResponse,
    ReviewSubmission,
)
from app.services.results import build_authoritative_result, payload_dict_from_extraction
from app.services.validation import InvoiceBusinessValidator

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewQueueItemResponse])
def list_reviews(
    review_status: Literal["pending", "completed", "superseded", "all"] = Query(
        default="pending", alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ReviewQueueItemResponse]:
    """List human-review work, pending by default."""
    statement = (
        select(Review)
        .options(
            selectinload(Review.document)
            .selectinload(Document.extractions)
            .selectinload(Extraction.line_items)
        )
        .order_by(Review.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    if review_status != "all":
        statement = statement.where(Review.review_status == review_status)

    reviews = list(db.scalars(statement).all())
    items: list[ReviewQueueItemResponse] = []
    for review in reviews:
        extraction = _latest_extraction(review.document)
        if extraction is None:
            continue
        items.append(_queue_item(review, extraction))
    return items


@router.get("/{document_id}", response_model=ReviewDetailResponse)
def get_review(document_id: str, db: Session = Depends(get_db)) -> ReviewDetailResponse:
    review = _get_latest_review(db, document_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")

    extraction = _latest_extraction(review.document)
    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review exists without an extraction candidate.",
        )
    return _detail_response(review, extraction)


@router.post("/{document_id}", response_model=ReviewDetailResponse)
def submit_review(
    document_id: str,
    submission: ReviewSubmission,
    db: Session = Depends(get_db),
    validator: InvoiceBusinessValidator = Depends(get_invoice_validator),
) -> ReviewDetailResponse:
    """Confirm or correct an AI candidate while preserving the original extraction."""
    review = _get_pending_review(db, document_id)
    if review is None:
        existing = _get_latest_review(db, document_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Review is already {existing.review_status}.",
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending review not found.")

    extraction = _latest_extraction(review.document)
    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review exists without an extraction candidate.",
        )

    corrections = submission.corrections.model_dump(mode="json", exclude_unset=True)
    merged_data = payload_dict_from_extraction(extraction)
    merged_data.update(corrections)

    try:
        authoritative_payload = InvoiceExtractionPayload.model_validate(merged_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Human corrections do not satisfy the invoice schema.",
                "errors": exc.errors(include_url=False),
            },
        ) from exc

    validation = validator.validate(authoritative_payload, check_confidence=False)
    if validation.review_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Human corrections still violate business validation rules.",
                "validation_errors": [issue.to_dict() for issue in validation.issues],
            },
        )

    review.corrected_values_json = corrections
    review.corrected_by = submission.corrected_by
    review.corrected_at = datetime.now(timezone.utc)
    review.review_status = "completed"
    review.document.processing_status = "reviewed"
    db.commit()

    review = _get_latest_review(db, document_id)
    if review is None:
        raise RuntimeError("Review disappeared after persistence.")
    extraction = _latest_extraction(review.document)
    if extraction is None:
        raise RuntimeError("Extraction disappeared after review persistence.")
    return _detail_response(review, extraction)


def _get_pending_review(db: Session, document_id: str) -> Review | None:
    statement = (
        select(Review)
        .where(Review.document_id == document_id, Review.review_status == "pending")
        .options(
            selectinload(Review.document)
            .selectinload(Document.extractions)
            .selectinload(Extraction.line_items)
        )
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    return db.scalar(statement)


def _get_latest_review(db: Session, document_id: str) -> Review | None:
    statement = (
        select(Review)
        .where(Review.document_id == document_id)
        .options(
            selectinload(Review.document)
            .selectinload(Document.extractions)
            .selectinload(Extraction.line_items)
        )
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    return db.scalar(statement)


def _latest_extraction(document: Document) -> Extraction | None:
    if not document.extractions:
        return None
    return max(document.extractions, key=lambda extraction: extraction.created_at)


def _queue_item(review: Review, extraction: Extraction) -> ReviewQueueItemResponse:
    return ReviewQueueItemResponse(
        review_id=review.id,
        document_id=review.document_id,
        original_filename=review.document.original_filename,
        review_status=review.review_status,
        reason=review.reason,
        created_at=review.created_at,
        invoice_number=extraction.invoice_number,
        vendor_name=extraction.vendor_name,
        total=extraction.total,
        currency=extraction.currency,
        ai_confidence=extraction.ai_confidence,
        validation_errors=extraction.validation_errors,
    )


def _detail_response(review: Review, extraction: Extraction) -> ReviewDetailResponse:
    corrections = review.corrected_values_json or {}
    authoritative = build_authoritative_result(extraction, corrections)
    return ReviewDetailResponse(
        review_id=review.id,
        document_id=review.document_id,
        original_filename=review.document.original_filename,
        review_status=review.review_status,
        reason=review.reason,
        created_at=review.created_at,
        corrected_by=review.corrected_by,
        corrected_at=review.corrected_at,
        corrections=review.corrected_values_json,
        original_extraction=ExtractionResponse.model_validate(extraction),
        authoritative_result=authoritative,
    )
