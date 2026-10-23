import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from ontherecord.models.base import Base, UUIDPrimaryKey


class RefreshToken(UUIDPrimaryKey, Base):
    """One refresh token. Only its SHA-256 is stored, so a database leak can't be
    replayed. Each use rotates it: the old row is marked used and a new row joins
    the same family (one family = one signed-in device)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    # Set when rotated. Presenting a used token again means it was copied: the family is revoked.
    used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=10)
