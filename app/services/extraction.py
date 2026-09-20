from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.models.document import Document
from app.schemas.extraction import InvoiceExtractionPayload


EXTRACTION_INSTRUCTIONS = """You extract invoice data from business documents.
Return only information visible in the supplied document.
Do not guess or infer missing values. Use null for nullable invoice header fields that cannot be determined.
Use ISO dates (YYYY-MM-DD), three-letter uppercase currency codes, and numeric values without currency symbols.
Confidence must be a number from 0 to 1 representing confidence in the extraction as a whole.
Line items must preserve the document's visible item descriptions and numeric values; do not invent missing line-item numbers.
"""


class ResponsesAPI(Protocol):
    def parse(self, **kwargs: Any) -> Any: ...


class AIClient(Protocol):
    responses: ResponsesAPI


class AIExtractionError(RuntimeError):
    """Raised when the provider cannot return valid structured invoice data."""


class AIConfigurationError(RuntimeError):
    """Raised when the extraction provider is not configured."""


@dataclass(frozen=True)
class AIExtractionResult:
    payload: InvoiceExtractionPayload
    model_used: str
    provider_response_id: str | None


class InvoiceExtractor:
    """Send one stored document to the AI provider and require typed output."""

    def __init__(self, settings: Settings, client: AIClient | None = None) -> None:
        self.settings = settings
        self._client = client

    def extract(self, document: Document) -> AIExtractionResult:
        client = self._client or self._build_client()
        content = self._build_content(document)
        last_error: Exception | None = None

        for _attempt in range(1, self.settings.ai_max_attempts + 1):
            try:
                response = client.responses.parse(
                    model=self.settings.ai_model,
                    instructions=EXTRACTION_INSTRUCTIONS,
                    input=[{"role": "user", "content": content}],
                    text_format=InvoiceExtractionPayload,
                )
                parsed = getattr(response, "output_parsed", None)
                if parsed is None:
                    raise ValueError("Provider response did not contain parsed structured output.")
                if not isinstance(parsed, InvoiceExtractionPayload):
                    parsed = InvoiceExtractionPayload.model_validate(parsed)

                return AIExtractionResult(
                    payload=parsed,
                    model_used=self.settings.ai_model,
                    provider_response_id=getattr(response, "id", None),
                )
            except Exception as exc:  # Provider/transport/structured-output errors are retryable here.
                last_error = exc

        raise AIExtractionError(
            f"Invoice extraction failed after {self.settings.ai_max_attempts} attempts."
        ) from last_error

    def _build_client(self) -> AIClient:
        if self.settings.ai_provider.lower() != "openai":
            raise AIConfigurationError(f"Unsupported AI_PROVIDER: {self.settings.ai_provider}")
        if not self.settings.ai_api_key:
            raise AIConfigurationError("AI_API_KEY is not configured.")

        # Lazy import keeps unit tests independent from the external SDK.
        from openai import OpenAI

        return OpenAI(api_key=self.settings.ai_api_key)

    @staticmethod
    def _build_content(document: Document) -> list[dict[str, Any]]:
        path = Path(document.storage_path)
        if not path.is_file():
            raise AIExtractionError("Stored document file is missing.")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        prompt = {
            "type": "input_text",
            "text": "Extract the invoice fields from this document using the required schema.",
        }

        if document.content_type == "application/pdf":
            file_part = {
                "type": "input_file",
                "filename": document.original_filename,
                "file_data": f"data:application/pdf;base64,{encoded}",
            }
            return [file_part, prompt]

        if document.content_type in {"image/png", "image/jpeg"}:
            image_part = {
                "type": "input_image",
                "image_url": f"data:{document.content_type};base64,{encoded}",
                "detail": "auto",
            }
            return [image_part, prompt]

        raise AIExtractionError(f"Unsupported stored content type: {document.content_type}")
