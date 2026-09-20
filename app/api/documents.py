from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.services.storage import FileTooLargeError, StorageValidationError, save_upload

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Document:
    """Validate, store, and persist metadata for one uploaded document."""
    document_id = str(uuid4())

    try:
        stored = await save_upload(
            file,
            upload_dir=settings.upload_dir,
            max_upload_mb=settings.max_upload_mb,
            document_id=document_id,
        )
    except FileTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except StorageValidationError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    document = Document(
        id=document_id,
        original_filename=stored.original_filename,
        stored_filename=stored.stored_filename,
        content_type=stored.content_type,
        file_size_bytes=stored.file_size_bytes,
        storage_path=str(stored.storage_path),
        processing_status="uploaded",
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        Path(stored.storage_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The file could not be recorded in the database.",
        ) from exc

    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Document]:
    """Return document metadata, newest uploads first."""
    statement = select(Document).order_by(Document.uploaded_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)) -> Document:
    """Return metadata for one uploaded document."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document
