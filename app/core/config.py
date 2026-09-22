from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env."""

    app_name: str = "AI Document Review Pipeline"
    app_env: str = "development"
    database_url: str = "sqlite:///./document_review.db"
    upload_dir: Path = Path("storage/uploads")
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    ai_provider: str = "openai"
    ai_model: str = "replace-with-document-capable-model"
    ai_api_key: str = ""
    ai_max_attempts: int = Field(default=2, ge=1, le=5)
    ai_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
    amount_tolerance: float = Field(default=0.01, gt=0, le=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def require_postgresql_in_production(self) -> "Settings":
        """Prevent accidental production startup against the development SQLite database."""
        if self.app_env.lower() == "production":
            backend = make_url(self.database_url).get_backend_name()
            if backend != "postgresql":
                raise ValueError("APP_ENV=production requires a PostgreSQL DATABASE_URL.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
