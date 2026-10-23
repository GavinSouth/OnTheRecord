import pytest

from ontherecord.config import Settings


def test_reads_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTR_ENV", "prod")
    monkeypatch.setenv("OTR_DATABASE_URL", "postgresql+psycopg://u@h/db")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env == "prod"
    assert settings.database_url == "postgresql+psycopg://u@h/db"


def test_rejects_unknown_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTR_ENV", "staging")
    monkeypatch.setenv("OTR_DATABASE_URL", "postgresql+psycopg://u@h/db")
    with pytest.raises(ValueError, match="env"):
        Settings(_env_file=None)  # type: ignore[call-arg]
