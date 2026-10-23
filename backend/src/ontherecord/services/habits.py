"""Habits and their daily checks. Every query is scoped to the user (D2)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ontherecord.models import CheckStatus, Habit, HabitCheck, User
from ontherecord.schemas.habit import HabitCreate, HabitUpdate
from ontherecord.services.clock import local_date, user_today
from ontherecord.services.errors import ConflictError, InvalidInputError, NotFoundError
from ontherecord.services.habit_stats import Schedule

MAX_HEATMAP_DAYS = 731  # two years


def _live_habits(user: User) -> Select[Habit]:
    return select(Habit).where(Habit.user_id == user.id, Habit.deleted_at.is_(None))


def schedule_of(user: User, habit: Habit) -> Schedule:
    # Archiving stops expectations from the archive day on (that day isn't expected).
    ends_on = None
    if habit.archived_at is not None:
        ends_on = local_date(user, habit.archived_at) - timedelta(days=1)
    return Schedule(habit.schedule_days, habit.started_on, ends_on)


def list_habits(session: Session, user: User, *, include_archived: bool) -> Sequence[Habit]:
    query = _live_habits(user).order_by(Habit.position, Habit.created_at)
    if not include_archived:
        query = query.where(Habit.archived_at.is_(None))
    return session.scalars(query).all()


def get_habit(session: Session, user: User, habit_id: uuid.UUID) -> Habit:
    habit = session.scalars(_live_habits(user).where(Habit.id == habit_id)).one_or_none()
    if habit is None:
        raise NotFoundError("Habit not found")
    return habit


def create_habit(session: Session, user: User, data: HabitCreate) -> Habit:
    if data.id is not None and session.get(Habit, data.id) is not None:
        raise ConflictError("A habit with this id already exists")
    position = data.position
    if position is None:
        last = session.scalar(
            select(func.max(Habit.position)).where(
                Habit.user_id == user.id, Habit.deleted_at.is_(None)
            )
        )
        position = (last or 0.0) + 1.0
    habit = Habit(
        user_id=user.id,
        name=data.name,
        description=data.description,
        color=data.color,
        schedule_days=data.schedule_days,
        started_on=data.started_on or user_today(user),
        position=position,
    )
    if data.id is not None:
        habit.id = data.id
    session.add(habit)
    session.commit()
    return habit


def update_habit(session: Session, habit: Habit, data: HabitUpdate) -> Habit:
    changes = data.model_dump(exclude_unset=True)
    if "archived" in changes:
        archived = changes.pop("archived")
        if archived and habit.archived_at is None:
            habit.archived_at = datetime.now(UTC)
        elif not archived:
            habit.archived_at = None
    for field, value in changes.items():
        setattr(habit, field, value)
    session.commit()
    return habit


def delete_habit(session: Session, habit: Habit) -> None:
    habit.deleted_at = datetime.now(UTC)
    session.commit()


def set_check(
    session: Session, user: User, habit: Habit, day: date, status: CheckStatus
) -> HabitCheck:
    """Idempotent: the same request twice leaves one row. Re-checking an unchecked
    day revives its row instead of inserting a second one."""
    if habit.archived_at is not None:
        raise ConflictError("Habit is archived; unarchive it to record checks")
    if day > user_today(user):
        raise InvalidInputError("Cannot check a future day")
    if day < habit.started_on:
        raise InvalidInputError("Day is before the habit's started_on")
    stmt = (
        insert(HabitCheck)
        .values(user_id=user.id, habit_id=habit.id, date=day, status=status)
        .on_conflict_do_update(
            index_elements=[HabitCheck.habit_id, HabitCheck.date],
            set_={"status": status, "deleted_at": None, "updated_at": func.now()},
        )
        .returning(HabitCheck)
        .execution_options(populate_existing=True)
    )
    check = session.scalars(stmt).one()
    session.commit()
    return check


def clear_check(session: Session, habit: Habit, day: date) -> None:
    """Uncheck = soft delete (D8). Clearing an unchecked day is a no-op."""
    session.execute(
        update(HabitCheck)
        .where(
            HabitCheck.habit_id == habit.id,
            HabitCheck.date == day,
            HabitCheck.deleted_at.is_(None),
        )
        .values(deleted_at=func.now(), updated_at=func.now())
    )
    session.commit()


def list_checks(
    session: Session, habit_ids: Sequence[uuid.UUID], start: date, end: date
) -> Sequence[HabitCheck]:
    return session.scalars(
        select(HabitCheck)
        .where(
            HabitCheck.habit_id.in_(habit_ids),
            HabitCheck.date.between(start, end),
            HabitCheck.deleted_at.is_(None),
        )
        .order_by(HabitCheck.date)
    ).all()


def checks_by_habit(
    checks: Sequence[HabitCheck],
) -> defaultdict[uuid.UUID, dict[date, CheckStatus]]:
    grouped: defaultdict[uuid.UUID, dict[date, CheckStatus]] = defaultdict(dict)
    for check in checks:
        grouped[check.habit_id][check.date] = check.status
    return grouped


def heatmap_range(user: User, start: date | None, end: date | None) -> tuple[date, date]:
    """Defaults to the last 365 days ending today."""
    end = end or user_today(user)
    start = start or end - timedelta(days=364)
    if start > end:
        raise InvalidInputError("`from` must be on or before `to`")
    if (end - start).days + 1 > MAX_HEATMAP_DAYS:
        raise InvalidInputError(f"Range is limited to {MAX_HEATMAP_DAYS} days")
    return start, end
