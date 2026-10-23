"""Fixtures against a real Postgres (D4).

The test database (`OTR_TEST_DATABASE_URL`) is created if missing and migrated
from scratch once per run, which also exercises every migration's up and down.
Each test then runs inside a transaction that is rolled back, so tests never see
each other's rows.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ontherecord.config import Settings
from ontherecord.db import get_session
from ontherecord.main import create_app
from ontherecord.models import User
from ontherecord.services.auth import issue_access_token

BACKEND_DIR = Path(__file__).resolve().parents[1]

MakeApp = Callable[..., FastAPI]

TEST_JWT_SECRET = "test-only-secret-at-least-32-characters-long"
TEST_APPLE_CLIENT_ID = "com.example.ontherecord"


class DatabaseEnv(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OTR_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    test_database_url: str


def _ensure_database(url: str) -> None:
    """CREATE DATABASE (which can't run in a transaction) if it doesn't exist yet."""
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    try:
        url = DatabaseEnv().test_database_url  # type: ignore[call-arg]
    except ValidationError:
        pytest.fail(
            "OTR_TEST_DATABASE_URL is not set. Copy backend/.env.example to backend/.env.",
            pytrace=False,
        )
    try:
        _ensure_database(url)
    except OperationalError as exc:
        pytest.fail(
            f"Can't reach the test Postgres ({exc.orig}).\n"
            "Start it from backend/: `docker compose up -d` (see .env.example).",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    cfg = Config(BACKEND_DIR / "alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False  # keep pytest's log capture intact
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as conn:
        outer = conn.begin()
        yield conn
        outer.rollback()


@pytest.fixture
def db_session(connection: Connection) -> Iterator[Session]:
    # Commits inside the code under test become SAVEPOINT releases; the outer
    # transaction (rolled back above) is never committed.
    with Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    ) as session:
        yield session


@pytest.fixture
def make_app(database_url: str) -> MakeApp:
    """Build an app on the test database; keyword args override settings."""

    def _make(**overrides: object) -> FastAPI:
        settings = Settings.model_validate(
            {
                "env": "test",
                "database_url": database_url,
                "jwt_secret": TEST_JWT_SECRET,
                "apple_client_ids": [TEST_APPLE_CLIENT_ID],
            }
            | overrides
        )
        return create_app(settings)

    return _make


def _signed_in_client(app: FastAPI, session: Session, apple_sub: str, name: str) -> TestClient:
    """A client sending a real access token, so every test goes through the real auth path."""
    user = User(apple_sub=apple_sub, display_name=name)
    session.add(user)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    token = issue_access_token(user.id, app.state.settings)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def client(make_app: MakeApp, db_session: Session) -> Iterator[TestClient]:
    with _signed_in_client(make_app(), db_session, "test-user", "Test User") as c:
        yield c


@pytest.fixture
def other_client(make_app: MakeApp, db_session: Session) -> Iterator[TestClient]:
    """A second, unrelated user on the same database: for user-scoping tests (D2)."""
    with _signed_in_client(make_app(), db_session, "other-user", "Other User") as c:
        yield c
