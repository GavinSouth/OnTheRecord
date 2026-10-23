import uuid

from sqlalchemy import Computed, ForeignKey, Index
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from ontherecord.models.base import Base, SoftDelete, Timestamps, UUIDPrimaryKey


class Note(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    """A Markdown note (D10). Maps 1:1 to an Obsidian file later."""

    __tablename__ = "notes"
    __table_args__ = (
        # Newest-first pages: (created_at, id) is the cursor.
        Index("ix_notes_user_id_created_at_id", "user_id", "created_at", "id"),
        Index("ix_notes_search", "search", postgresql_using="gin"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    body: Mapped[str]
    # Full-text index, kept up to date by Postgres itself (a generated column).
    # English stemming: "running" matches "run". Never loaded into Python.
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', body)", persisted=True), deferred=True
    )
