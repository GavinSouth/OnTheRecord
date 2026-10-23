from sqlalchemy.orm import Mapped, mapped_column

from ontherecord.models.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    # Sign in with Apple's stable user id (F2.5). The dev stub uses a fixed placeholder.
    apple_sub: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str | None]
    display_name: Mapped[str] = mapped_column(server_default="")
    # IANA name; defines "today" for habit streaks (D8).
    timezone: Mapped[str] = mapped_column(server_default="UTC")
