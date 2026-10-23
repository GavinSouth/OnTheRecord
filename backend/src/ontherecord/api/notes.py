import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from ontherecord.api.deps import CurrentUser, SessionDep
from ontherecord.schemas.note import NoteCreate, NotePage, NoteRead, NoteUpdate
from ontherecord.services import notes as service

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("")
def list_notes(
    session: SessionDep,
    user: CurrentUser,
    q: Annotated[
        str | None,
        Query(max_length=200, description='Full-text search: words, "phrases", or, -word'),
    ] = None,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotePage:
    """Newest first. With `q`, only matching notes (still newest first)."""
    notes, next_cursor = service.list_notes(session, user, q=q, cursor=cursor, limit=limit)
    return NotePage(notes=[NoteRead.model_validate(n) for n in notes], next_cursor=next_cursor)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(session: SessionDep, user: CurrentUser, body: NoteCreate) -> NoteRead:
    return NoteRead.model_validate(service.create_note(session, user, body))


@router.get("/{note_id}")
def read_note(session: SessionDep, user: CurrentUser, note_id: uuid.UUID) -> NoteRead:
    return NoteRead.model_validate(service.get_note(session, user, note_id))


@router.patch("/{note_id}")
def update_note(
    session: SessionDep, user: CurrentUser, note_id: uuid.UUID, body: NoteUpdate
) -> NoteRead:
    note = service.get_note(session, user, note_id)
    return NoteRead.model_validate(service.update_note(session, note, body))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(session: SessionDep, user: CurrentUser, note_id: uuid.UUID) -> None:
    service.delete_note(session, service.get_note(session, user, note_id))
