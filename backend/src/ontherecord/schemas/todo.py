import uuid
from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from ontherecord.models import TodoEventType

ListName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Notes = Annotated[str, StringConstraints(max_length=10_000)]


def _reject_nulls(model: BaseModel, nullable: set[str]) -> None:
    """In a PATCH, omitted = unchanged and null = clear. Only `nullable` fields may be null."""
    nulled = {f for f in model.model_fields_set if getattr(model, f) is None} - nullable
    if nulled:
        raise ValueError(f"cannot be null: {', '.join(sorted(nulled))}")


# --- lists ---


class TodoListCreate(BaseModel):
    id: uuid.UUID | None = Field(None, description="Client-generated id (optional)")
    name: ListName
    parent_id: uuid.UUID | None = Field(None, description="Containing list; null = top level")
    position: float | None = Field(None, description="Defaults to the end of its siblings")


class TodoListUpdate(BaseModel):
    """Rename, move (`parent_id`; null = top level) or reorder (`position`)."""

    name: ListName | None = None
    parent_id: uuid.UUID | None = None
    position: float | None = None

    @model_validator(mode="after")
    def _nulls(self) -> Self:
        _reject_nulls(self, {"parent_id"})
        return self


class TodoListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    position: float
    open_count: int = Field(0, description="Open items directly in this list")
    created_at: datetime
    updated_at: datetime


# --- items ---


class TodoItemCreate(BaseModel):
    id: uuid.UUID | None = Field(None, description="Client-generated id (optional)")
    title: Title
    notes: Notes | None = None
    due_date: date | None = None
    position: float | None = Field(None, description="Defaults to the end of the list")


class TodoItemUpdate(BaseModel):
    """Edit, move (`list_id`), reorder (`position`), or complete/reopen (`completed`)."""

    title: Title | None = None
    notes: Notes | None = None
    due_date: date | None = None
    list_id: uuid.UUID | None = None
    position: float | None = None
    completed: bool | None = None

    @model_validator(mode="after")
    def _nulls(self) -> Self:
        _reject_nulls(self, {"notes", "due_date"})
        return self


class TodoItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    list_id: uuid.UUID
    title: str
    notes: str | None
    due_date: date | None
    position: float
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completed(self) -> bool:
        return self.completed_at is not None


# --- history ---


class TodoEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    type: TodoEventType
    data: dict[str, Any]
    occurred_at: datetime


class TodoEventPage(BaseModel):
    events: list[TodoEventRead]
    next_cursor: uuid.UUID | None = Field(description="Pass as `after` for the next page")
