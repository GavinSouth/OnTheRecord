"""Notes: CRUD, newest-first keyset pagination, and Postgres full-text search."""

import base64
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.orm import Session

from ontherecord.models import Note, User
from ontherecord.schemas.note import NoteCreate, NoteUpdate
from ontherecord.services.errors import ConflictError, InvalidInputError, NotFoundError


def _live_notes(user: User) -> Select[Note]:
    return select(Note).where(Note.user_id == user.id, Note.deleted_at.is_(None))


def get_note(session: Session, user: User, note_id: uuid.UUID) -> Note:
    note = session.scalars(_live_notes(user).where(Note.id == note_id)).one_or_none()
    if note is None:
        raise NotFoundError("Note not found")
    return note


def create_note(session: Session, user: User, data: NoteCreate) -> Note:
    if data.id is not None and session.get(Note, data.id) is not None:
        raise ConflictError("A note with this id already exists")
    note = Note(user_id=user.id, body=data.body)
    if data.id is not None:
        note.id = data.id
    session.add(note)
    session.commit()
    return note


def update_note(session: Session, note: Note, data: NoteUpdate) -> Note:
    note.body = data.body
    session.commit()
    return note


def delete_note(session: Session, note: Note) -> None:
    note.deleted_at = datetime.now(UTC)
    session.commit()


# --- listing ---
# Keyset ("seek") pagination: each page asks for rows strictly older than the last
# one seen, using (created_at, id). Unlike OFFSET, it stays fast on any page and
# never skips or repeats a note when new ones are added meanwhile. `id` breaks
# ties, and also works for client-supplied ids that don't sort by time.


def encode_cursor(note: Note) -> str:
    raw = json.dumps([note.created_at.isoformat(), str(note.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Cursors are opaque to clients; anything malformed is a 422, not a 500."""
    try:
        created_at, note_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created_at), uuid.UUID(note_id)
    except (ValueError, TypeError) as exc:
        raise InvalidInputError("Invalid cursor") from exc


def list_notes(
    session: Session, user: User, *, q: str | None, cursor: str | None, limit: int
) -> tuple[Sequence[Note], str | None]:
    """Newest first. `q` uses web-search syntax: words (stemmed, all must match),
    "quoted phrases", `or`, and `-excluded` words. Returns (notes, next_cursor)."""
    query = _live_notes(user)
    if q and q.strip():
        query = query.where(Note.search.bool_op("@@")(func.websearch_to_tsquery("english", q)))
    if cursor is not None:
        created_at, note_id = decode_cursor(cursor)
        query = query.where(tuple_(Note.created_at, Note.id) < tuple_(created_at, note_id))
    rows = session.scalars(
        query.order_by(Note.created_at.desc(), Note.id.desc()).limit(limit + 1)
    ).all()
    if len(rows) > limit:
        return rows[:limit], encode_cursor(rows[limit - 1])
    return rows, None
