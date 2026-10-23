import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from ontherecord.api.deps import CurrentUser, SessionDep
from ontherecord.schemas.habit import (
    CheckRead,
    CheckWrite,
    HabitCreate,
    HabitDay,
    HabitRead,
    HabitStats,
    HabitUpdate,
    HabitWithDay,
    Heatmap,
    HeatmapDay,
)
from ontherecord.services import habits as service
from ontherecord.services.clock import user_today
from ontherecord.services.habit_stats import compute_heatmap, compute_stats

router = APIRouter(prefix="/habits", tags=["habits"])

From = Annotated[date | None, Query(alias="from", description="Inclusive start date")]
To = Annotated[date | None, Query(alias="to", description="Inclusive end date")]


@router.get("")
def list_habits(
    session: SessionDep,
    user: CurrentUser,
    for_date: Annotated[date | None, Query(description="Adds that day's check status")] = None,
    include_archived: bool = False,
) -> list[HabitWithDay]:
    habits = service.list_habits(session, user, include_archived=include_archived)
    if for_date is None:
        return [HabitWithDay.model_validate(h) for h in habits]
    checks = service.checks_by_habit(
        service.list_checks(session, [h.id for h in habits], for_date, for_date)
    )
    return [
        HabitWithDay.model_validate(h).model_copy(
            update={
                "day": HabitDay(
                    date=for_date,
                    scheduled=service.schedule_of(user, h).expects(for_date),
                    status=checks[h.id].get(for_date),
                )
            }
        )
        for h in habits
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_habit(session: SessionDep, user: CurrentUser, body: HabitCreate) -> HabitRead:
    return HabitRead.model_validate(service.create_habit(session, user, body))


# Declared before /{habit_id} so "heatmap" isn't parsed as an id.
@router.get("/heatmap")
def heatmap(
    session: SessionDep,
    user: CurrentUser,
    start: From = None,
    end: To = None,
    habit_id: uuid.UUID | None = None,
) -> Heatmap:
    """Per day: how many habits were expected, done and skipped. All live habits
    (archived ones keep their history) or one habit with `habit_id`. Default range:
    the last 365 days."""
    start, end = service.heatmap_range(user, start, end)
    if habit_id is None:
        habits = service.list_habits(session, user, include_archived=True)
    else:
        habits = [service.get_habit(session, user, habit_id)]
    checks = service.checks_by_habit(
        service.list_checks(session, [h.id for h in habits], start, end)
    )
    days = compute_heatmap(
        [service.schedule_of(user, h) for h in habits], [checks[h.id] for h in habits], start, end
    )
    return Heatmap(
        start=start,
        end=end,
        habit_id=habit_id,
        days=[HeatmapDay.model_validate(d) for d in days],
    )


@router.get("/{habit_id}")
def read_habit(session: SessionDep, user: CurrentUser, habit_id: uuid.UUID) -> HabitRead:
    return HabitRead.model_validate(service.get_habit(session, user, habit_id))


@router.patch("/{habit_id}")
def update_habit(
    session: SessionDep, user: CurrentUser, habit_id: uuid.UUID, body: HabitUpdate
) -> HabitRead:
    """Edit, reorder, or archive (`archived: true`) / unarchive."""
    habit = service.get_habit(session, user, habit_id)
    return HabitRead.model_validate(service.update_habit(session, habit, body))


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(session: SessionDep, user: CurrentUser, habit_id: uuid.UUID) -> None:
    service.delete_habit(session, service.get_habit(session, user, habit_id))


@router.get("/{habit_id}/stats")
def habit_stats(session: SessionDep, user: CurrentUser, habit_id: uuid.UUID) -> HabitStats:
    habit = service.get_habit(session, user, habit_id)
    today = user_today(user)
    checks = service.checks_by_habit(
        service.list_checks(session, [habit.id], habit.started_on, today)
    )
    stats = compute_stats(service.schedule_of(user, habit), checks[habit.id], today)
    return HabitStats(as_of=today, **vars(stats))


@router.get("/{habit_id}/checks")
def list_checks(
    session: SessionDep,
    user: CurrentUser,
    habit_id: uuid.UUID,
    start: From = None,
    end: To = None,
) -> list[CheckRead]:
    """Recorded days (done/skipped), oldest first. Default: started_on → today."""
    habit = service.get_habit(session, user, habit_id)
    checks = service.list_checks(
        session, [habit.id], start or habit.started_on, end or user_today(user)
    )
    return [CheckRead.model_validate(c) for c in checks]


@router.put("/{habit_id}/checks/{day}")
def set_check(
    session: SessionDep, user: CurrentUser, habit_id: uuid.UUID, day: date, body: CheckWrite
) -> CheckRead:
    """Record `done` or `skipped` for a local day. Idempotent."""
    habit = service.get_habit(session, user, habit_id)
    return CheckRead.model_validate(service.set_check(session, user, habit, day, body.status))


@router.delete("/{habit_id}/checks/{day}", status_code=status.HTTP_204_NO_CONTENT)
def clear_check(session: SessionDep, user: CurrentUser, habit_id: uuid.UUID, day: date) -> None:
    """Uncheck a day. Idempotent."""
    service.clear_check(session, service.get_habit(session, user, habit_id), day)
