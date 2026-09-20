from app.core.config import Settings


def test_default_settings_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite")
    assert settings.max_upload_mb == 10
    assert settings.ai_api_key == ""
    assert settings.ai_confidence_threshold == 0.80
    assert settings.amount_tolerance == 0.01
