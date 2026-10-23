"""Settings read from the environment (and `backend/.env` in local dev)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Every field maps to an `OTR_`-prefixed env var, e.g. `OTR_DATABASE_URL`."""

    model_config = SettingsConfigDict(env_prefix="OTR_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@localhost:5432/ontherecord
    database_url: str


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read once."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
