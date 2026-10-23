import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


# Markdown is whitespace-sensitive, so the body is stored exactly as sent.
Body = Annotated[str, StringConstraints(max_length=100_000), AfterValidator(_not_blank)]


class NoteCreate(BaseModel):
    id: uuid.UUID | None = Field(None, description="Client-generated id (optional)")
    body: Body


class NoteUpdate(BaseModel):
    body: Body


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime


class NotePage(BaseModel):
    notes: list[NoteRead]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next (older) page")
