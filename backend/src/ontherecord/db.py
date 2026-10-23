"""Database engine and the per-request session dependency."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    # pre_ping replaces connections the server dropped (restarts, idle timeouts).
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit, so a route can
    # commit and then serialise what it just wrote.
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """One session per request. Routes and services commit explicitly; anything
    uncommitted is rolled back when the session closes."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session
