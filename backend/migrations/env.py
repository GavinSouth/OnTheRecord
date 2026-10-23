"""Alembic environment. Runs migrations online against the configured database.

URL: `sqlalchemy.url` if the caller set one (tests do), else
`OTR_MIGRATIONS_DATABASE_URL` (the table owner, in prod), else `OTR_DATABASE_URL`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from ontherecord.config import get_settings
from ontherecord.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        settings = get_settings()
        url = settings.migrations_database_url or settings.database_url
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not set up; run against a database.")
run_migrations()
