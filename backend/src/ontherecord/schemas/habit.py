import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from ontherecord.models import CheckStatus, HabitColor

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
ScheduleDays = Annotated[
    list[Annotated[int, Field(ge=1, le=7)]],
    Field(min_length=1, max_length=7, description="ISO weekdays: Mon=1 … Sun=7"),
    AfterValidator(lambda v: sorted(set(v))),
]
EVERY_DAY = [1, 2, 3, 4, 5, 6, 7]


class HabitCreate(BaseModel):
    id: uuid.UUID | None = Field(None, description="Client-generated id (optional)")
    name: Name
    description: Description | None = None
    color: HabitColor = HabitColor.GREEN
    schedule_days: ScheduleDays = Field(default_factory=lambda: list(EVERY_DAY))
    started_on: date | None = Field(None, description="Defaults to the user's today")
    position: float | None = Field(None, description="Defaults to the end of the list")


class HabitUpdate(BaseModel):
    """Partial update: only fields present in the body change."""

    name: Name | None = None
    description: Description | None = None
    color: HabitColor | None = None
    schedule_days: ScheduleDays | None = None
    started_on: date | None = None
    position: float | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def _no_null_for_required(self) -> Self:
        # `description: null` clears it; the rest can be omitted but not nulled.
        nulled = {f for f in self.model_fields_set if getattr(self, f) is None} - {"description"}
        if nulled:
            raise ValueError(f"cannot be null: {', '.join(sorted(nulled))}")
        return self


class HabitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    color: HabitColor
    schedule_days: list[int]
    started_on: date
    position: float
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def archived(self) -> bool:
        return self.archived_at is not None


class HabitDay(BaseModel):
    """A habit's state on one day: the iOS Today view."""

    date: date
    scheduled: bool
    status: CheckStatus | None


class HabitWithDay(HabitRead):
    day: HabitDay | None = Field(None, description="Present when `for_date` is given")


class CheckWrite(BaseModel):
    status: CheckStatus = CheckStatus.DONE


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    status: CheckStatus
    updated_at: datetime


class HabitStats(BaseModel):
    as_of: date
    current_streak: int
    longest_streak: int
    done_count: int
    skipped_count: int
    missed_count: int
    expected_count: int = Field(description="Scheduled days decided so far (done or missed)")
    completion_rate: float | None = Field(description="0–1; null before any day is decided")


class HeatmapDay(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    scheduled: int
    done: int
    skipped: int


class Heatmap(BaseModel):
    start: date
    end: date
    habit_id: uuid.UUID | None
    days: list[HeatmapDay]
