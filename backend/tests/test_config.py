import pytest

from ontherecord.config import Settings
from tests.conftest import TEST_JWT_SECRET


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("OTR_DATABASE_URL", "postgresql+psycopg://u@h/db")
    monkeypatch.setenv("OTR_JWT_SECRET", TEST_JWT_SECRET)
    return monkeypatch


def test_reads_prefixed_env(base_env: pytest.MonkeyPatch) -> None:
    base_env.setenv("OTR_ENV", "prod")
    base_env.setenv("OTR_APPLE_CLIENT_IDS", '["com.example.app", "com.example.web"]')
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env == "prod"
    assert settings.database_url == "postgresql+psycopg://u@h/db"
    assert settings.apple_client_ids == ["com.example.app", "com.example.web"]


def test_rejects_unknown_env(base_env: pytest.MonkeyPatch) -> None:
    base_env.setenv("OTR_ENV", "staging")
    with pytest.raises(ValueError, match="env"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_rejects_short_jwt_secret(base_env: pytest.MonkeyPatch) -> None:
    base_env.setenv("OTR_JWT_SECRET", "change-me")
    with pytest.raises(ValueError, match="jwt_secret"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_prod_requires_apple_client_ids(base_env: pytest.MonkeyPatch) -> None:
    base_env.setenv("OTR_ENV", "prod")
    with pytest.raises(ValueError, match="apple_client_ids"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secret_is_hidden_in_repr(base_env: pytest.MonkeyPatch) -> None:
    assert TEST_JWT_SECRET not in repr(Settings(_env_file=None))  # type: ignore[call-arg]
