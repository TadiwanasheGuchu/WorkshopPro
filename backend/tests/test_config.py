import pytest

from app.core.config import Settings


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://garage.example.na")

    settings = Settings()

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://garage.example.na"]


def test_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().is_production is True


def test_secure_cookies_follow_environment_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COOKIE_SECURE", "")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().secure_cookies is True
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert Settings().secure_cookies is False
    monkeypatch.setenv("COOKIE_SECURE", "true")
    assert Settings().secure_cookies is True


def test_production_refuses_unsafe_settings() -> None:
    import pytest

    from app.core.config import Settings
    from app.main import create_app

    unsafe = Settings(
        environment="production",
        app_base_url="http://workshop.example.na",
        cors_allowed_origins=["http://localhost:3000"],
        smtp_host="mailpit",
        storage_access_key="key",
        storage_secret_key="change-me-local-only",
        whatsapp_provider="meta",
    )
    problems = unsafe.production_problems()
    assert any("APP_BASE_URL" in p for p in problems)
    assert any("CORS" in p for p in problems)
    assert any("SMTP_HOST" in p for p in problems)
    assert any("STORAGE_SECRET_KEY" in p for p in problems)
    assert any("WHATSAPP" in p for p in problems)
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        create_app(unsafe)

    safe = Settings(
        environment="production",
        app_base_url="https://workshop.kalahari.na",
        cors_allowed_origins=["https://workshop.kalahari.na"],
        database_url="postgresql+psycopg://wp:Strong-Db-Pass-91@postgres:5432/workshoppro",
        smtp_host="smtp.mailprovider.na",
        storage_access_key="wp-storage",
        storage_secret_key="Strong-Storage-Secret-74",
    )
    assert safe.production_problems() == []
    assert create_app(safe) is not None
