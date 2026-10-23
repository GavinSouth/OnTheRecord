import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

TODAY = datetime.now(UTC).date()  # the dev user's timezone is UTC


def new_list(client: TestClient, name: str = "Home", **body: Any) -> dict[str, Any]:
    res = client.post("/api/v1/lists", json={"name": name, **body})
    assert res.status_code == 201, res.text
    data: dict[str, Any] = res.json()
    return data


def new_item(client: TestClient, list_id: str, title: str = "Milk", **body: Any) -> dict[str, Any]:
    res = client.post(f"/api/v1/lists/{list_id}/items", json={"title": title, **body})
    assert res.status_code == 201, res.text
    data: dict[str, Any] = res.json()
    return data


def patch_item(client: TestClient, item_id: str, **body: Any) -> Any:
    return client.patch(f"/api/v1/items/{item_id}", json=body)


def event_types(client: TestClient, item_id: str) -> list[str]:
    return [e["type"] for e in client.get(f"/api/v1/items/{item_id}/events").json()]


# --- lists ---


def test_lists_nest_and_come_back_flat(client: TestClient) -> None:
    home = new_list(client, "Home")
    kitchen = new_list(client, "Kitchen", parent_id=home["id"])
    garden = new_list(client, "Garden", parent_id=home["id"])
    work = new_list(client, "Work")

    lists = {lst["name"]: lst for lst in client.get("/api/v1/lists").json()}
    assert lists["Kitchen"]["parent_id"] == lists["Garden"]["parent_id"] == home["id"]
    assert lists["Home"]["parent_id"] is None
    # Positions append among siblings, not globally.
    assert kitchen["position"] < garden["position"]
    assert work["position"] == home["position"] + 1


def test_open_count(client: TestClient) -> None:
    lst = new_list(client)
    new_item(client, lst["id"], "A")
    done = new_item(client, lst["id"], "B")
    patch_item(client, done["id"], completed=True)
    assert client.get("/api/v1/lists").json()[0]["open_count"] == 1


def test_rename_and_move_to_top_level(client: TestClient) -> None:
    home = new_list(client, "Home")
    child = new_list(client, "Kitchen", parent_id=home["id"])
    res = client.patch(f"/api/v1/lists/{child['id']}", json={"name": "Pantry", "parent_id": None})
    assert res.status_code == 200
    assert (res.json()["name"], res.json()["parent_id"]) == ("Pantry", None)


def test_moves_that_would_create_a_cycle_are_rejected(client: TestClient) -> None:
    a = new_list(client, "A")
    b = new_list(client, "B", parent_id=a["id"])
    c = new_list(client, "C", parent_id=b["id"])
    for target in (a, c):  # into itself, into its grandchild
        res = client.patch(f"/api/v1/lists/{a['id']}", json={"parent_id": target["id"]})
        assert res.status_code == 409
    # Moving a leaf up is fine.
    assert client.patch(f"/api/v1/lists/{c['id']}", json={"parent_id": a["id"]}).status_code == 200


def test_move_into_unknown_list_is_404(client: TestClient) -> None:
    a = new_list(client)
    res = client.patch(f"/api/v1/lists/{a['id']}", json={"parent_id": str(uuid.uuid4())})
    assert res.status_code == 404


def test_list_patch_rejects_null_name(client: TestClient) -> None:
    a = new_list(client)
    assert client.patch(f"/api/v1/lists/{a['id']}", json={"name": None}).status_code == 422


def test_deleting_a_list_deletes_its_subtree(client: TestClient) -> None:
    home = new_list(client, "Home")
    kitchen = new_list(client, "Kitchen", parent_id=home["id"])
    shelf = new_list(client, "Shelf", parent_id=kitchen["id"])
    work = new_list(client, "Work")
    deep_item = new_item(client, shelf["id"], "Jam")
    work_item = new_item(client, work["id"], "Email")

    assert client.delete(f"/api/v1/lists/{home['id']}").status_code == 204

    assert [lst["name"] for lst in client.get("/api/v1/lists").json()] == ["Work"]
    assert client.get(f"/api/v1/items/{deep_item['id']}").status_code == 404
    assert client.get(f"/api/v1/items/{work_item['id']}").status_code == 200
    events = client.get(f"/api/v1/items/{deep_item['id']}/events").json()
    assert events[-1]["type"] == "deleted"
    assert events[-1]["data"] == {"via_list_id": home["id"]}
    # A deleted list can't take new items.
    assert client.post(f"/api/v1/lists/{shelf['id']}/items", json={"title": "x"}).status_code == 404


# --- items ---


def test_create_item_logs_created(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"], due_date=TODAY.isoformat(), notes="2%")
    assert item["completed"] is False
    events = client.get(f"/api/v1/items/{item['id']}/events").json()
    assert [(e["type"], e["data"]) for e in events] == [
        ("created", {"title": "Milk", "list_id": lst["id"]})
    ]


def test_client_supplied_item_id(client: TestClient) -> None:
    lst = new_list(client)
    item_id = str(uuid.uuid4())
    assert new_item(client, lst["id"], id=item_id)["id"] == item_id
    res = client.post(f"/api/v1/lists/{lst['id']}/items", json={"id": item_id, "title": "x"})
    assert res.status_code == 409


@pytest.mark.parametrize("body", [{"title": ""}, {"title": "  "}, {"title": "x" * 501}])
def test_item_validation(client: TestClient, body: dict[str, Any]) -> None:
    lst = new_list(client)
    assert client.post(f"/api/v1/lists/{lst['id']}/items", json=body).status_code == 422


def test_edit_logs_changed_fields_only(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    patch_item(client, item["id"], title="Oat milk", due_date=TODAY.isoformat())
    patch_item(client, item["id"], title="Oat milk")  # no change → no event

    events = client.get(f"/api/v1/items/{item['id']}/events").json()
    assert [e["type"] for e in events] == ["created", "edited"]
    assert events[1]["data"] == {
        "changes": {
            "title": {"from": "Milk", "to": "Oat milk"},
            "due_date": {"from": None, "to": TODAY.isoformat()},
        }
    }


def test_complete_and_reopen(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    res = patch_item(client, item["id"], completed=True)
    assert res.json()["completed"] is True
    patch_item(client, item["id"], completed=True)  # already done: no second event
    assert patch_item(client, item["id"], completed=False).json()["completed_at"] is None
    assert event_types(client, item["id"]) == ["created", "completed", "reopened"]


def test_completed_filter_and_order(client: TestClient) -> None:
    lst = new_list(client)
    a, b, c = (new_item(client, lst["id"], t) for t in "ABC")
    patch_item(client, a["id"], completed=True)
    patch_item(client, c["id"], completed=True)

    def titles(**params: Any) -> list[str]:
        res = client.get(f"/api/v1/lists/{lst['id']}/items", params=params)
        return [i["title"] for i in res.json()]

    assert titles() == ["A", "B", "C"]
    assert titles(completed=False) == ["B"]
    assert titles(completed=True) == ["C", "A"]  # most recently completed first


def test_move_item_between_lists(client: TestClient) -> None:
    home, work = new_list(client, "Home"), new_list(client, "Work")
    new_item(client, work["id"], "Existing")
    item = new_item(client, home["id"])
    res = patch_item(client, item["id"], list_id=work["id"])
    assert res.json()["list_id"] == work["id"]
    assert res.json()["position"] == 2.0  # end of the target list
    events = client.get(f"/api/v1/items/{item['id']}/events").json()
    assert events[-1]["data"] == {"from_list_id": home["id"], "to_list_id": work["id"]}
    assert patch_item(client, item["id"], list_id=str(uuid.uuid4())).status_code == 404


def test_reorder_logs_nothing(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    assert patch_item(client, item["id"], position=0.5).json()["position"] == 0.5
    assert event_types(client, item["id"]) == ["created"]


def test_one_patch_can_log_several_events(client: TestClient) -> None:
    home, work = new_list(client, "Home"), new_list(client, "Work")
    item = new_item(client, home["id"])
    patch_item(client, item["id"], title="Eggs", list_id=work["id"], completed=True)
    assert event_types(client, item["id"]) == ["created", "edited", "moved", "completed"]


def test_item_patch_rejects_null_title(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    assert patch_item(client, item["id"], title=None).status_code == 422
    assert patch_item(client, item["id"], notes=None).status_code == 200


def test_deleted_item_keeps_its_history(client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    assert client.delete(f"/api/v1/items/{item['id']}").status_code == 204
    assert client.get(f"/api/v1/items/{item['id']}").status_code == 404
    assert event_types(client, item["id"]) == ["created", "deleted"]


# --- history ---


def test_todo_events_paginate_with_a_cursor(client: TestClient) -> None:
    lst = new_list(client)
    for title in "ABCDE":
        new_item(client, lst["id"], title)

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["after"] = cursor
        page = client.get("/api/v1/todo-events", params=params).json()
        seen += [e["data"]["title"] for e in page["events"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list("ABCDE")
    assert pages == 3


def test_todo_events_date_range(client: TestClient) -> None:
    new_item(client, new_list(client)["id"])
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    in_range = client.get("/api/v1/todo-events", params={"from": TODAY.isoformat()}).json()
    before = client.get("/api/v1/todo-events", params={"to": yesterday}).json()
    assert len(in_range["events"]) == 1
    assert before["events"] == []


def test_events_cannot_be_rewritten(client: TestClient, db_session: Session) -> None:
    new_item(client, new_list(client)["id"])
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("UPDATE todo_events SET type = 'edited'"))
    db_session.rollback()


# --- user scoping (D2) ---


def test_users_never_see_each_others_todos(client: TestClient, other_client: TestClient) -> None:
    lst = new_list(client)
    item = new_item(client, lst["id"])
    theirs = new_list(other_client, "Theirs")

    assert [x["name"] for x in other_client.get("/api/v1/lists").json()] == ["Theirs"]
    assert other_client.get(f"/api/v1/lists/{lst['id']}/items").status_code == 404
    assert (
        other_client.post(f"/api/v1/lists/{lst['id']}/items", json={"title": "x"}).status_code
        == 404
    )
    assert other_client.patch(f"/api/v1/lists/{lst['id']}", json={"name": "x"}).status_code == 404
    assert other_client.delete(f"/api/v1/lists/{lst['id']}").status_code == 404
    assert other_client.get(f"/api/v1/items/{item['id']}").status_code == 404
    assert other_client.get(f"/api/v1/items/{item['id']}/events").status_code == 404
    assert other_client.get("/api/v1/todo-events").json()["events"] == []
    # Nor can anyone move their own things into someone else's list.
    assert patch_item(client, item["id"], list_id=theirs["id"]).status_code == 404
    res = client.patch(f"/api/v1/lists/{lst['id']}", json={"parent_id": theirs["id"]})
    assert res.status_code == 404
