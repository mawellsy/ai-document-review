from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Public metadata returned for an uploaded document."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    processing_status: str
    uploaded_at: datetime
