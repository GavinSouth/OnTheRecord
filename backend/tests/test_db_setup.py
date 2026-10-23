"""Least-privilege roles (docs/HOSTING.md): what each role can and can't do."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, make_url, text
from sqlalchemy.exc import ProgrammingError

from ontherecord.db_setup import APP, OWNER, READONLY, SetupError, setup_database
from tests.conftest import as_role


def _maintenance(admin_database_url: str) -> str:
    return make_url(admin_database_url).set(database="postgres").render_as_string(False)


@pytest.fixture
def readonly(admin_database_url: str) -> Iterator[Connection]:
    engine = create_engine(as_role(admin_database_url, READONLY))
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_suite_runs_as_app_role(connection: Connection) -> None:
    assert connection.scalar(text("SELECT current_user")) == APP


def test_tables_belong_to_owner(connection: Connection) -> None:
    owners = connection.scalars(
        text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'")
    ).all()
    assert owners == [OWNER]


def test_app_reads_and_writes_rows(connection: Connection) -> None:
    connection.execute(text("INSERT INTO users (apple_sub) VALUES ('grant-check')"))
    assert connection.scalar(text("SELECT count(*) FROM users WHERE apple_sub = 'grant-check'"))


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE sneaky (id int)",
        "DROP TABLE notes",
        "ALTER TABLE users ADD COLUMN sneaky int",
        "TRUNCATE users",
        "DROP TRIGGER todo_events_no_update ON todo_events",
    ],
)
def test_app_cannot_change_the_schema(connection: Connection, statement: str) -> None:
    """A bug or SQL injection in the API can't destroy tables."""
    with pytest.raises(ProgrammingError, match="permission denied|must be owner"):
        connection.execute(text(statement))


def test_readonly_can_select_but_not_write(readonly: Connection) -> None:
    assert readonly.scalar(text("SELECT count(*) FROM users")) is not None
    with pytest.raises(ProgrammingError, match="permission denied"):
        readonly.execute(text("INSERT INTO users (apple_sub) VALUES ('nope')"))


def test_setup_is_idempotent(admin_database_url: str) -> None:
    """Re-running (e.g. after migrations) only re-applies grants."""
    name = make_url(admin_database_url).database
    assert name
    assert setup_database(_maintenance(admin_database_url), name, passwords=False) == {}


def test_setup_refuses_a_database_with_another_owner(admin_database_url: str) -> None:
    admin = create_engine(_maintenance(admin_database_url), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS otr_setup_probe"))
        conn.execute(text("CREATE DATABASE otr_setup_probe"))  # owned by the superuser
        try:
            with pytest.raises(SetupError, match="owned by"):
                setup_database(_maintenance(admin_database_url), "otr_setup_probe", passwords=False)
        finally:
            conn.execute(text("DROP DATABASE otr_setup_probe"))
    admin.dispose()
