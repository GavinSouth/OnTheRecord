import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontherecord.models.base import Base, SoftDelete, Timestamps, UUIDPrimaryKey, text_enum


class TodoList(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    """A list that can also hold lists, so lists double as folders. Moves are
    checked for cycles in the service layer."""

    __tablename__ = "todo_lists"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("todo_lists.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    position: Mapped[float]


class TodoItem(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "todo_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("todo_lists.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str]
    notes: Mapped[str | None]  # Markdown
    due_date: Mapped[date | None]
    position: Mapped[float]
    completed_at: Mapped[datetime | None]


class TodoEventType(enum.StrEnum):
    CREATED = "created"
    EDITED = "edited"
    COMPLETED = "completed"
    REOPENED = "reopened"
    MOVED = "moved"
    DELETED = "deleted"
    RESTORED = "restored"


class TodoEvent(UUIDPrimaryKey, Base):
    """Append-only history of item changes (D9). Written in the same transaction as
    the change; a database trigger rejects UPDATEs (migration 0003)."""

    __tablename__ = "todo_events"
    __table_args__ = (Index("ix_todo_events_user_id_occurred_at", "user_id", "occurred_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("todo_items.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[TodoEventType] = mapped_column(text_enum(TodoEventType, "todo_event_type"))
    # e.g. {"changes": {"title": {"from": "a", "to": "b"}}}, {"from_list_id": …, "to_list_id": …}
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
