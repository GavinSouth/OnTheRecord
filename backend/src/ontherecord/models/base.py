"""Declarative base and the columns every table shares."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names, so Alembic can find (and drop) them later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # All timestamps are timestamptz, stored in UTC (ARCHITECTURE › Data model).
    type_annotation_map = {datetime: DateTime(timezone=True)}


class UUIDPrimaryKey:
    """UUID id. Clients may supply one (D6); otherwise Postgres 18 generates a UUIDv7."""

    # sort_order: id first, bookkeeping columns last, whatever the mixin order.
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("uuidv7()"), sort_order=-10
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=10)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), sort_order=10
    )


class SoftDelete:
    """Rows are hidden, not removed (D7): sync and history need to know what went away."""

    deleted_at: Mapped[datetime | None] = mapped_column(sort_order=11)


def text_enum(cls: type[enum.StrEnum], name: str) -> Enum:
    """varchar + CHECK instead of a native Postgres enum: adding a value later is a
    one-line constraint change instead of ALTER TYPE."""
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda e: [m.value for m in e],
    )
