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

    # --- Email ---
    # "smtp" sends through the server below. "log" records that a message was sent
    # (recipient domain and subject only, never the body) without sending: for demos
    # without a mail server. Not allowed in production.
    email_provider: Literal["smtp", "log"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    email_from: str = "WorkshopPro <no-reply@workshoppro.local>"

    # --- Object storage ---
    # "s3": any S3-compatible service (SeaweedFS in Compose). "database": bytes kept in
    # PostgreSQL (table stored_objects) for hosts without object storage or a disk, such
    # as the free hosted demo. Fine for small volumes; use S3 for real installations.
    storage_backend: Literal["s3", "database"] = "s3"
    storage_endpoint_url: str | None = "http://localhost:8333"
    storage_bucket: str = "workshoppro"
    # Credentials must come from the environment; there is no usable default.
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"
    storage_auto_create_bucket: bool = True

    # --- Background jobs (Celery, Redis broker) ---
    # Eager mode runs tasks in-process; used by tests and single-process development.
    celery_eager: bool = False

    # --- WhatsApp (official WhatsApp Business Platform only; never WhatsApp Web) ---
    # "log" records messages without sending; "meta" uses the Cloud API and needs the
    # credentials below from the environment or a secrets manager.
    whatsapp_provider: Literal["log", "meta"] = "log"
    whatsapp_api_base: str = "https://graph.facebook.com/v21.0"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    # Used to verify webhook signatures (X-Hub-Signature-256) and the subscription.
    whatsapp_app_secret: str = ""
    whatsapp_webhook_verify_token: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def _psycopg_driver(cls, value: object) -> object:
        # Hosted databases (Neon, Render) hand out postgres:// or postgresql:// URLs;
        # SQLAlchemy needs the psycopg (v3) driver named explicitly.
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

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

    def production_problems(self) -> list[str]:
        """Settings that are unsafe for a production installation. The API refuses to start
        in production while any remain (see create_app)."""
        problems: list[str] = []
        placeholders = ("change-me", "changeme", "example")
        if not self.app_base_url.startswith("https://"):
            problems.append("APP_BASE_URL must use https://")
        for origin in self.cors_allowed_origins:
            if origin == "*" or not origin.startswith("https://") or "localhost" in origin:
                problems.append(f"CORS_ALLOWED_ORIGINS contains a non-production origin: {origin}")
        if self.cookie_secure is False:
            problems.append("COOKIE_SECURE must not be false in production")
        if any(p in str(self.database_url) for p in placeholders):
            problems.append("DATABASE_URL still uses a placeholder password")
        if self.email_provider == "log":
            problems.append("EMAIL_PROVIDER=log does not send email; use smtp in production")
        if self.storage_backend == "s3" and (
            not self.storage_access_key or not self.storage_secret_key
        ):
            problems.append("STORAGE_ACCESS_KEY and STORAGE_SECRET_KEY must be set")
        elif self.storage_backend == "s3" and any(
            p in self.storage_secret_key for p in placeholders
        ):
            problems.append("STORAGE_SECRET_KEY still uses a placeholder value")
        if self.smtp_host in ("mailpit", "localhost", "127.0.0.1"):
            problems.append("SMTP_HOST points at the local development mail catcher")
        if self.whatsapp_provider == "meta" and not (
            self.whatsapp_phone_number_id
            and self.whatsapp_access_token
            and self.whatsapp_app_secret
        ):
            problems.append(
                "WHATSAPP_PROVIDER=meta needs WHATSAPP_PHONE_NUMBER_ID, "
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_APP_SECRET"
            )
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED must be true in production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
