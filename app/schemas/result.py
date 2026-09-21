from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.review import AuthoritativeInvoiceResponse


class FinalDocumentResultResponse(BaseModel):
    document_id: str
    original_filename: str
    processing_status: str
    extraction_id: str
    result_source: Literal["ai_validated", "human_reviewed"]
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    authoritative_result: AuthoritativeInvoiceResponse
