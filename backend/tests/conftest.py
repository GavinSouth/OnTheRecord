"""Fixtures against a real Postgres (D4).

The test database (`OTR_TEST_DATABASE_URL`) is recreated once per run with the
production roles (`ontherecord.db_setup`), then migrated as `otr_owner` up, down
and up again, which exercises every migration. Tests and the app connect as
`otr_app`, so a missing grant fails here before it fails in prod. Each test runs
inside a transaction that is rolled back, so tests never see each other's rows.

The test login must be a superuser (the Compose and CI one is): it switches roles
with SET ROLE, so the roles need no passwords.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
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
from ontherecord.db_setup import APP, OWNER, setup_database
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


def _recreate_database(url: str) -> None:
    """Drop the test database and create it again the way prod is set up."""
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
    finally:
        admin.dispose()
    assert target.database
    maintenance = target.set(database="postgres").render_as_string(hide_password=False)
    setup_database(maintenance, target.database, passwords=False)


def as_role(url: str, role: str) -> str:
    """The same login, acting as `role` from connect time on (`SET ROLE`)."""
    return (
        make_url(url)
        .update_query_dict({"options": f"-c role={role}"})
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="session")
def admin_database_url() -> str:
    """The test database as the superuser test login: for setup and role tests only."""
    try:
        url = DatabaseEnv().test_database_url  # type: ignore[call-arg]
    except ValidationError:
        pytest.fail(
            "OTR_TEST_DATABASE_URL is not set. Copy backend/.env.example to backend/.env.",
            pytrace=False,
        )
    try:
        _recreate_database(url)
    except (OperationalError, psycopg.OperationalError) as exc:
        pytest.fail(
            f"Can't reach the test Postgres ({exc}).\n"
            "Start it from backend/: `docker compose up -d` (see .env.example).",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def database_url(admin_database_url: str) -> str:
    """The test database as the API sees it: connected as `otr_app`."""
    return as_role(admin_database_url, APP)


@pytest.fixture(scope="session")
def engine(admin_database_url: str, database_url: str) -> Iterator[Engine]:
    cfg = Config(BACKEND_DIR / "alembic.ini")
    owner_url = as_role(admin_database_url, OWNER)
    cfg.set_main_option("sqlalchemy.url", owner_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False  # keep pytest's log capture intact
    command.upgrade(cfg, "head")
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
