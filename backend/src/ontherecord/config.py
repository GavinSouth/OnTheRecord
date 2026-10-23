"""Settings read from the environment (and `backend/.env` in local dev)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Every field maps to an `OTR_`-prefixed env var, e.g. `OTR_DATABASE_URL`."""

    model_config = SettingsConfigDict(env_prefix="OTR_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@localhost:5432/ontherecord
    database_url: str
    # Alembic connects with this instead when set: in prod the API runs as `otr_app`
    # (rows only) and migrations as `otr_owner` (owns the tables). See docs/HOSTING.md.
    migrations_database_url: str | None = None

    # Signs access tokens (HS256). Generate one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(15, gt=0)
    refresh_token_days: int = Field(60, gt=0)
    # Accepted `aud` values in Apple identity tokens: the iOS bundle id and the web
    # Services ID. JSON list in the env, e.g. OTR_APPLE_CLIENT_IDS='["com.example.app"]'.
    apple_client_ids: list[str] = []

    @model_validator(mode="after")
    def _prod_can_sign_in(self) -> Self:
        if self.env == "prod" and not self.apple_client_ids:
            raise ValueError("apple_client_ids is required in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read once."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
