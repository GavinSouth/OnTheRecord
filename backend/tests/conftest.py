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

from ontherecord.api.deps import get_current_user
from ontherecord.config import Settings
from ontherecord.db import get_session
from ontherecord.main import create_app
from ontherecord.models import User

BACKEND_DIR = Path(__file__).resolve().parents[1]

MakeApp = Callable[..., FastAPI]


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
            {"env": "test", "database_url": database_url} | overrides
        )
        return create_app(settings)

    return _make


@pytest.fixture
def client(make_app: MakeApp, db_session: Session) -> Iterator[TestClient]:
    app = make_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client(make_app: MakeApp, db_session: Session) -> Iterator[TestClient]:
    """A second, unrelated user on the same database: for user-scoping tests (D2)."""
    other = User(apple_sub="other-user", display_name="Other User")
    db_session.add(other)
    db_session.commit()
    app = make_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: other
    with TestClient(app) as c:
        yield c
