import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from ontherecord.models import Note


def new_note(client: TestClient, body: str, **extra: Any) -> dict[str, Any]:
    res = client.post("/api/v1/notes", json={"body": body, **extra})
    assert res.status_code == 201, res.text
    data: dict[str, Any] = res.json()
    return data


def bodies(client: TestClient, **params: Any) -> list[str]:
    res = client.get("/api/v1/notes", params=params)
    assert res.status_code == 200, res.text
    return [n["body"] for n in res.json()["notes"]]


# --- CRUD ---


def test_create_read_update_delete(client: TestClient) -> None:
    note = new_note(client, "# Idea\n\n- *call* Sam  \n")
    assert note["body"] == "# Idea\n\n- *call* Sam  \n"  # Markdown kept byte-for-byte
    url = f"/api/v1/notes/{note['id']}"

    assert client.get(url).json()["body"] == note["body"]
    assert client.patch(url, json={"body": "Updated"}).json()["body"] == "Updated"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert bodies(client) == []


def test_client_supplied_id(client: TestClient) -> None:
    note_id = str(uuid.uuid4())
    assert new_note(client, "a", id=note_id)["id"] == note_id
    assert client.post("/api/v1/notes", json={"id": note_id, "body": "b"}).status_code == 409


@pytest.mark.parametrize("body", ["", "   \n ", "x" * 100_001])
def test_body_validation(client: TestClient, body: str) -> None:
    assert client.post("/api/v1/notes", json={"body": body}).status_code == 422


# --- newest first + cursor pagination ---


def _age(db_session: Session, note: dict[str, Any], minutes: int) -> None:
    """Backdate a note: inside the test transaction every row gets the same now()."""
    when = datetime.now(UTC) - timedelta(minutes=minutes)
    db_session.execute(update(Note).where(Note.id == note["id"]).values(created_at=when))


def test_newest_first(client: TestClient, db_session: Session) -> None:
    _age(db_session, new_note(client, "old"), 10)
    _age(db_session, new_note(client, "new"), 1)
    _age(db_session, new_note(client, "middle"), 5)
    assert bodies(client) == ["new", "middle", "old"]


def test_cursor_walks_every_note_once(client: TestClient) -> None:
    # Same created_at for all five (one transaction), so the id tie-breaker decides.
    for n in range(5):
        new_note(client, f"note {n}")
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get("/api/v1/notes", params=params).json()
        seen += [n["body"] for n in page["notes"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"note {n}" for n in reversed(range(5))]


def test_new_notes_dont_shift_later_pages(client: TestClient) -> None:
    for n in range(3):
        new_note(client, f"note {n}")
    first = client.get("/api/v1/notes", params={"limit": 2}).json()
    new_note(client, "added while paging")
    rest = client.get("/api/v1/notes", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [n["body"] for n in rest["notes"]] == ["note 0"]


@pytest.mark.parametrize("cursor", ["nope", "bm9wZQ==", "WyJ4IiwgInkiXQ=="])
def test_bad_cursor_is_422(client: TestClient, cursor: str) -> None:
    assert client.get("/api/v1/notes", params={"cursor": cursor}).status_code == 422


# --- full-text search ---


@pytest.fixture
def notes(client: TestClient) -> None:
    for body in (
        "Went running by the river",
        "Book: The Pragmatic Programmer",
        "Call the dentist about Thursday",
        "Dentist moved to Friday",
    ):
        new_note(client, body)


@pytest.mark.usefixtures("notes")
@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("run", ["Went running by the river"]),  # stemming: run ≈ running
        ("DENTIST", ["Dentist moved to Friday", "Call the dentist about Thursday"]),
        ("dentist -friday", ["Call the dentist about Thursday"]),  # exclusion
        ("dentist thursday", ["Call the dentist about Thursday"]),  # all words must match
        ('"pragmatic programmer"', ["Book: The Pragmatic Programmer"]),  # phrase
        ("river or friday", ["Dentist moved to Friday", "Went running by the river"]),
        ("piano", []),
        ("   ", None),  # blank = no filter
    ],
)
def test_search(client: TestClient, q: str, expected: list[str] | None) -> None:
    result = bodies(client, q=q)
    if expected is None:
        assert len(result) == 4
    else:
        assert result == expected


def test_search_follows_edits_and_skips_deleted(client: TestClient) -> None:
    note = new_note(client, "Buy flowers")
    client.patch(f"/api/v1/notes/{note['id']}", json={"body": "Buy chocolate"})
    assert bodies(client, q="flowers") == []
    assert bodies(client, q="chocolate") == ["Buy chocolate"]
    client.delete(f"/api/v1/notes/{note['id']}")
    assert bodies(client, q="chocolate") == []


# --- user scoping (D2) ---


def test_users_never_see_each_others_notes(client: TestClient, other_client: TestClient) -> None:
    note = new_note(client, "Private thought")
    url = f"/api/v1/notes/{note['id']}"
    assert bodies(other_client) == []
    assert bodies(other_client, q="private") == []
    assert other_client.get(url).status_code == 404
    assert other_client.patch(url, json={"body": "x"}).status_code == 404
    assert other_client.delete(url).status_code == 404
    assert client.get(url).json()["body"] == "Private thought"
