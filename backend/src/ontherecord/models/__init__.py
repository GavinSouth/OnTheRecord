"""SQLAlchemy models. Import every model here so `Base.metadata` (and Alembic) sees it."""

from ontherecord.models.base import Base
from ontherecord.models.user import User

__all__ = ["Base", "User"]
