"""Application settings loaded from environment variables.

Secrets must come from the environment (or a secrets manager in production),
never from source control. See `.env.example` at the repository root.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WorkshopPro"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    database_url: PostgresDsn = Field(
        default=PostgresDsn(
            "postgresql+psycopg://workshoppro:workshoppro@localhost:5432/workshoppro"
        ),
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))

    # Comma-separated list of allowed browser origins.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # Public URL of the web app; used to build links in emails.
    app_base_url: str = "http://localhost:3000"

    # --- Sessions ---
    session_idle_timeout_minutes: int = Field(default=12 * 60, ge=5)
    session_absolute_timeout_hours: int = Field(default=7 * 24, ge=1)
    # Secure cookies require HTTPS. Defaults to on in production.
    cookie_secure: bool | None = None

    # --- Tokens ---
    password_reset_token_minutes: int = Field(default=60, ge=5)
    invitation_token_days: int = Field(default=7, ge=1)

    # --- Rate limits (attempts per window) ---
    rate_limit_enabled: bool = True
    login_attempts_per_email: int = 10
    login_attempts_per_ip: int = 50
    login_window_seconds: int = 15 * 60
    password_reset_requests_per_ip: int = 10
    password_reset_window_seconds: int = 60 * 60

    # --- Email (SMTP) ---
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    email_from: str = "WorkshopPro <no-reply@workshoppro.local>"

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
