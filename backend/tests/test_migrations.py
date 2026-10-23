from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection

from ontherecord.models import Base


def test_migrations_match_models(connection: Connection) -> None:
    """The migrated schema equals what the models declare. Fails when a model
    changes without a migration (run `alembic revision --autogenerate`)."""
    diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
