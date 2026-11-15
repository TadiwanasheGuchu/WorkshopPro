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

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
