import enum
import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Index, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ontherecord.models.base import Base, SoftDelete, Timestamps, UUIDPrimaryKey, text_enum


class HabitColor(enum.StrEnum):
    """The six user-pickable habit colours (design system `habit-*` tokens)."""

    GREEN = "green"
    BLUE = "blue"
    ORANGE = "orange"
    PLUM = "plum"
    GOLD = "gold"
    SLATE = "slate"


class CheckStatus(enum.StrEnum):
    DONE = "done"
    SKIPPED = "skipped"  # sick, travel: neither counts nor breaks a streak (D8)


class Habit(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    __tablename__ = "habits"
    __table_args__ = (
        CheckConstraint(
            "cardinality(schedule_days) > 0 AND schedule_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]",
            name="schedule_days_valid",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    description: Mapped[str | None]
    color: Mapped[HabitColor] = mapped_column(
        text_enum(HabitColor, "habit_color"), server_default=HabitColor.GREEN.value
    )
    # ISO weekdays (Mon=1 … Sun=7), sorted. All seven = daily.
    schedule_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    # Misses only count from this local date.
    started_on: Mapped[date]
    position: Mapped[float]
    # Archived habits stop being expected but keep their history.
    archived_at: Mapped[datetime | None]


class HabitCheck(UUIDPrimaryKey, Timestamps, SoftDelete, Base):
    """One local calendar day of a habit (D8). Unchecking soft-deletes; re-checking
    the same day revives the row via upsert on (habit_id, date)."""

    __tablename__ = "habit_checks"
    __table_args__ = (
        UniqueConstraint("habit_id", "date"),
        # Heatmap: all of a user's checks in a date range.
        Index("ix_habit_checks_user_id_date", "user_id", "date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    habit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"))
    date: Mapped[date]
    status: Mapped[CheckStatus] = mapped_column(text_enum(CheckStatus, "check_status"))
