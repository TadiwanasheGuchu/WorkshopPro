import pytest

from app.core.config import Settings


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://garage.example.na")

    settings = Settings()

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://garage.example.na"]


def test_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().is_production is True
