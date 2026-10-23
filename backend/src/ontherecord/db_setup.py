"""Least-privilege roles and database (docs/HOSTING.md). Run once per server, as an admin.

    OTR_ADMIN_DATABASE_URL='postgresql://postgres:…@host:port/postgres' \\
        uv run ontherecord-db-setup [--database ontherecord] [--rotate-passwords]

Idempotent: creates whatever is missing and re-applies the grants, so it's safe to
re-run after migrations. New roles get a generated password, printed once as
ready-made connection URLs. Tests call `setup_database` without passwords.
"""

import argparse
import getpass
import os
import secrets
import sys

import psycopg
from psycopg import sql
from sqlalchemy import URL, make_url

OWNER = "otr_owner"  # owns the database and its tables; used only by migrations
APP = "otr_app"  # the API: read/write rows, no CREATE/DROP/ALTER/TRUNCATE
READONLY = "otr_readonly"  # you + external tools: SELECT only
ROLES = (OWNER, APP, READONLY)

# Run inside the target database. ON ALL covers tables that already exist; DEFAULT
# PRIVILEGES covers the ones future migrations (run as OWNER) will create.
GRANTS = (
    f"GRANT USAGE ON SCHEMA public TO {APP}, {READONLY}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP}",
    f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP}",
    f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {READONLY}",
    f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER} IN SCHEMA public"
    f" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP}",
    f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER} IN SCHEMA public"
    f" GRANT USAGE, SELECT ON SEQUENCES TO {APP}",
    f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER} IN SCHEMA public"
    f" GRANT SELECT ON TABLES TO {READONLY}",
)


class SetupError(Exception):
    """The server is in a state the setup won't change on its own."""


def _conninfo(url: str | URL) -> str:
    """A libpq connection string from a SQLAlchemy URL (drops the `+psycopg` driver)."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def setup_database(
    admin_url: str, database: str, *, passwords: bool = True, rotate: bool = False
) -> dict[str, str]:
    """Create the roles and `database` (owned by OWNER), then grant.

    Returns {role: password} for every password this run set: new roles, or all of
    them with `rotate`. `passwords=False` leaves roles without one (tests reach them
    with SET ROLE as a superuser, and must not reset a dev server's passwords).
    """
    changed: dict[str, str] = {}
    with psycopg.connect(_conninfo(admin_url), autocommit=True) as conn:
        for role in ROLES:
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            if not exists:
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            if passwords and (rotate or not exists):
                password = secrets.token_urlsafe(32)
                # Hashed client-side (SCRAM), so the plain password never reaches server logs.
                hashed = conn.pgconn.encrypt_password(password.encode(), role.encode()).decode()
                conn.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(hashed)
                    )
                )
                changed[role] = password
        # A default, not a lock (a session can turn it off): the SELECT-only grants are the guard.
        conn.execute(f"ALTER ROLE {READONLY} SET default_transaction_read_only = on")

        row = conn.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()
        db = sql.Identifier(database)
        if row is None:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(db, sql.Identifier(OWNER)))
        elif row[0] != OWNER:
            raise SetupError(
                f"database {database!r} exists but is owned by {row[0]!r}, not {OWNER!r}; "
                "its tables would be too. Drop it (if it's throwaway) or pick another name."
            )
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(db))
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                db, sql.Identifier(APP), sql.Identifier(READONLY)
            )
        )

    with psycopg.connect(
        _conninfo(make_url(admin_url).set(database=database)), autocommit=True
    ) as conn:
        for grant in GRANTS:
            conn.execute(grant)
    return changed


def main() -> None:
    """`uv run ontherecord-db-setup`: set up a server and print the new connection URLs."""
    parser = argparse.ArgumentParser(description="Set up the least-privilege roles and database.")
    parser.add_argument("--database", default="ontherecord")
    parser.add_argument(
        "--rotate-passwords", action="store_true", help="give every role a new password"
    )
    args = parser.parse_args()
    # From the environment or a hidden prompt, never argv: it would land in shell history.
    admin_url = os.environ.get("OTR_ADMIN_DATABASE_URL") or getpass.getpass(
        "Admin URL (postgresql://postgres:…@host:port/postgres): "
    )
    try:
        changed = setup_database(admin_url, args.database, rotate=args.rotate_passwords)
    except (SetupError, psycopg.Error) as exc:
        sys.exit(f"error: {exc}")

    print(f"Database {args.database!r} ready; roles: {', '.join(ROLES)}.")
    if not changed:
        print("No passwords changed (use --rotate-passwords for new ones).")
        return
    base = make_url(admin_url).set(drivername="postgresql+psycopg", database=args.database)
    for role, password in changed.items():
        url = base.set(username=role, password=password)
        print(f"  {role}: {url.render_as_string(hide_password=False)}")
    print("Shown once: store them now (password manager + host variables).")
