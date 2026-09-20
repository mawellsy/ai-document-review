from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


CHUNK_SIZE = 1024 * 1024

SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", ".pdf", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_SUBMITTED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
    "",
}


class StorageValidationError(ValueError):
    """Raised when an uploaded file fails format or content validation."""


class FileTooLargeError(StorageValidationError):
    """Raised when an upload exceeds the configured size limit."""


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    stored_filename: str
    content_type: str
    file_size_bytes: int
    storage_path: Path


def safe_original_filename(filename: str | None) -> str:
    """Keep only the basename so client-supplied paths cannot escape storage."""
    if not filename:
        return "upload"

    normalized = filename.replace("\\", "/").replace("\x00", "")
    name = normalized.rsplit("/", maxsplit=1)[-1].strip()
    return name or "upload"


def detect_format(header: bytes) -> tuple[str, str] | None:
    """Return canonical extension and MIME type from file signature bytes."""
    for signature, extension, content_type in SIGNATURES:
        if header.startswith(signature):
            return extension, content_type
    return None


def _validate_extension(original_filename: str, detected_extension: str) -> None:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise StorageValidationError("Only PDF, PNG, JPG, and JPEG files are allowed.")

    normalized_suffix = ".jpg" if suffix == ".jpeg" else suffix
    if normalized_suffix != detected_extension:
        raise StorageValidationError("The filename extension does not match the file contents.")


def _validate_submitted_content_type(content_type: str | None, detected_content_type: str) -> None:
    submitted = (content_type or "").lower()
    if submitted not in ALLOWED_SUBMITTED_CONTENT_TYPES:
        raise StorageValidationError("The submitted content type is not allowed.")

    if submitted not in {"", "application/octet-stream", detected_content_type}:
        raise StorageValidationError("The submitted content type does not match the file contents.")


async def save_upload(
    upload: UploadFile,
    upload_dir: Path,
    max_upload_mb: int,
    *,
    document_id: str | None = None,
) -> StoredUpload:
    """Validate an upload, stream it to disk, and return trustworthy metadata.

    The client filename is never used as the stored filename. File type is
    determined from signature bytes rather than trusting the MIME header alone.
    """
    original_filename = safe_original_filename(upload.filename)
    max_bytes = max_upload_mb * 1024 * 1024

    header = await upload.read(16)
    if not header:
        raise StorageValidationError("The uploaded file is empty.")

    detected = detect_format(header)
    if detected is None:
        raise StorageValidationError("File contents are not a supported PDF or image format.")

    detected_extension, detected_content_type = detected
    _validate_extension(original_filename, detected_extension)
    _validate_submitted_content_type(upload.content_type, detected_content_type)

    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = document_id or str(uuid4())
    stored_filename = f"{file_id}{detected_extension}"
    storage_path = upload_dir / stored_filename

    bytes_written = 0
    try:
        with storage_path.open("xb") as destination:
            chunk = header
            while chunk:
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise FileTooLargeError(
                        f"File exceeds the {max_upload_mb} MB upload limit."
                    )
                destination.write(chunk)
                chunk = await upload.read(CHUNK_SIZE)
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredUpload(
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=detected_content_type,
        file_size_bytes=bytes_written,
        storage_path=storage_path,
    )
