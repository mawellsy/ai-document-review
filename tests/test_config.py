import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_settings_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite")
    assert settings.max_upload_mb == 10
    assert settings.ai_api_key == ""
    assert settings.ai_confidence_threshold == 0.80
    assert settings.amount_tolerance == 0.01


def test_production_accepts_postgresql_database_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://app:secret@db.example.test:5432/document_review",
    )

    assert settings.app_env == "production"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_production_rejects_sqlite_database_url() -> None:
    with pytest.raises(ValidationError, match="requires a PostgreSQL DATABASE_URL"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="sqlite:///./document_review.db",
        )
