from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.result import FinalDocumentResultResponse
from app.services.results import (
    DocumentResultNotFoundError,
    DocumentResultNotReadyError,
    ResolvedDocumentResult,
    resolve_document_result,
)

router = APIRouter(prefix="/documents", tags=["results"])


@router.get("/{document_id}/result", response_model=FinalDocumentResultResponse)
def get_final_result(
    document_id: str,
    db: Session = Depends(get_db),
) -> FinalDocumentResultResponse:
    """Return the final authoritative invoice record for downstream API consumers."""
    return _response_from_resolved(_resolve_or_http(db, document_id))


@router.get("/{document_id}/exports/json")
def export_json(document_id: str, db: Session = Depends(get_db)) -> Response:
    """Download the final authoritative record as JSON."""
    resolved = _resolve_or_http(db, document_id)
    payload = _response_from_resolved(resolved).model_dump(mode="json")
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    filename = f"{_export_stem(resolved.document.original_filename)}-result.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{document_id}/exports/csv")
def export_csv(document_id: str, db: Session = Depends(get_db)) -> Response:
    """Download the final authoritative invoice as a line-item-oriented CSV."""
    resolved = _resolve_or_http(db, document_id)
    output = io.StringIO(newline="")
    fieldnames = [
        "document_id",
        "original_filename",
        "result_source",
        "reviewed_by",
        "reviewed_at",
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
        "field_sources_json",
        "line_item_number",
        "line_item_description",
        "line_item_quantity",
        "line_item_unit_price",
        "line_item_amount",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    authoritative = resolved.authoritative_result
    line_items = authoritative.line_items or [None]
    for index, item in enumerate(line_items, start=1):
        writer.writerow(
            {
                "document_id": resolved.document.id,
                "original_filename": resolved.document.original_filename,
                "result_source": resolved.result_source,
                "reviewed_by": resolved.review.corrected_by if resolved.review else "",
                "reviewed_at": (
                    resolved.review.corrected_at.isoformat()
                    if resolved.review and resolved.review.corrected_at
                    else ""
                ),
                "invoice_number": authoritative.invoice_number or "",
                "invoice_date": authoritative.invoice_date.isoformat() if authoritative.invoice_date else "",
                "vendor_name": authoritative.vendor_name or "",
                "vendor_address": authoritative.vendor_address or "",
                "customer_name": authoritative.customer_name or "",
                "subtotal": _decimal_text(authoritative.subtotal),
                "tax": _decimal_text(authoritative.tax),
                "total": _decimal_text(authoritative.total),
                "currency": authoritative.currency or "",
                "due_date": authoritative.due_date.isoformat() if authoritative.due_date else "",
                "field_sources_json": json.dumps(authoritative.field_sources, sort_keys=True),
                "line_item_number": index if item is not None else "",
                "line_item_description": item.description if item is not None else "",
                "line_item_quantity": str(item.quantity) if item is not None else "",
                "line_item_unit_price": _decimal_text(item.unit_price) if item is not None else "",
                "line_item_amount": _decimal_text(item.amount) if item is not None else "",
            }
        )

    filename = f"{_export_stem(resolved.document.original_filename)}-result.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_or_http(db: Session, document_id: str) -> ResolvedDocumentResult:
    try:
        return resolve_document_result(db, document_id)
    except DocumentResultNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except DocumentResultNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


def _response_from_resolved(resolved: ResolvedDocumentResult) -> FinalDocumentResultResponse:
    return FinalDocumentResultResponse(
        document_id=resolved.document.id,
        original_filename=resolved.document.original_filename,
        processing_status=resolved.document.processing_status,
        extraction_id=resolved.extraction.id,
        result_source=resolved.result_source,
        reviewed_by=resolved.review.corrected_by if resolved.review else None,
        reviewed_at=resolved.review.corrected_at if resolved.review else None,
        authoritative_result=resolved.authoritative_result,
    )


def _export_stem(original_filename: str) -> str:
    stem = Path(original_filename).stem
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return safe or "document"


def _decimal_text(value) -> str:
    return "" if value is None else format(value, "f")
