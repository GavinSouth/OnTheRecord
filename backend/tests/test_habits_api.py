import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ontherecord.models import HabitCheck

TODAY = datetime.now(UTC).date()  # the dev user's timezone is UTC


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    res = client.post("/api/v1/habits", json={"name": "Read", **body})
    assert res.status_code == 201, res.text
    data: dict[str, Any] = res.json()
    return data


def check(client: TestClient, habit_id: str, day: str, status: str = "done") -> Any:
    return client.put(f"/api/v1/habits/{habit_id}/checks/{day}", json={"status": status})


# --- habits CRUD ---


def test_create_applies_defaults(client: TestClient) -> None:
    habit = create(client)
    assert habit["color"] == "green"
    assert habit["schedule_days"] == [1, 2, 3, 4, 5, 6, 7]
    assert habit["started_on"] == TODAY.isoformat()
    assert habit["archived"] is False
    assert uuid.UUID(habit["id"]).version == 7


def test_new_habits_go_to_the_end(client: TestClient) -> None:
    first, second = create(client, name="A"), create(client, name="B")
    assert second["position"] > first["position"]
    names = [h["name"] for h in client.get("/api/v1/habits").json()]
    assert names == ["A", "B"]


def test_client_supplied_id_is_kept_and_duplicates_conflict(client: TestClient) -> None:
    habit_id = str(uuid.uuid4())
    assert create(client, id=habit_id)["id"] == habit_id
    res = client.post("/api/v1/habits", json={"id": habit_id, "name": "Again"})
    assert res.status_code == 409


def test_schedule_days_are_sorted_and_deduplicated(client: TestClient) -> None:
    assert create(client, schedule_days=[5, 1, 3, 1])["schedule_days"] == [1, 3, 5]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   "},
        {"name": "x" * 101},
        {"name": "Read", "schedule_days": []},
        {"name": "Read", "schedule_days": [0]},
        {"name": "Read", "schedule_days": [8]},
        {"name": "Read", "color": "red"},
    ],
)
def test_create_rejects_invalid_input(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/api/v1/habits", json=body).status_code == 422


def test_patch_changes_only_given_fields(client: TestClient) -> None:
    habit = create(client, description="20 pages")
    res = client.patch(f"/api/v1/habits/{habit['id']}", json={"name": "Read more"})
    assert res.json()["name"] == "Read more"
    assert res.json()["description"] == "20 pages"
    res = client.patch(f"/api/v1/habits/{habit['id']}", json={"description": None})
    assert res.json()["description"] is None


def test_patch_rejects_null_for_required_fields(client: TestClient) -> None:
    habit = create(client)
    res = client.patch(f"/api/v1/habits/{habit['id']}", json={"name": None})
    assert res.status_code == 422


def test_archive_hides_from_default_list(client: TestClient) -> None:
    habit = create(client)
    res = client.patch(f"/api/v1/habits/{habit['id']}", json={"archived": True})
    assert res.json()["archived"] is True
    assert client.get("/api/v1/habits").json() == []
    archived = client.get("/api/v1/habits", params={"include_archived": True}).json()
    assert [h["id"] for h in archived] == [habit["id"]]
    res = client.patch(f"/api/v1/habits/{habit['id']}", json={"archived": False})
    assert res.json()["archived_at"] is None


def test_delete_hides_the_habit(client: TestClient) -> None:
    habit = create(client)
    assert client.delete(f"/api/v1/habits/{habit['id']}").status_code == 204
    assert client.get(f"/api/v1/habits/{habit['id']}").status_code == 404
    assert client.get("/api/v1/habits", params={"include_archived": True}).json() == []


def test_unknown_habit_is_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/habits/{uuid.uuid4()}").status_code == 404


# --- checks ---


def test_check_is_idempotent(client: TestClient, db_session: Session) -> None:
    habit = create(client)
    first = check(client, habit["id"], ago(0))
    second = check(client, habit["id"], ago(0))
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "done"
    assert db_session.scalar(select(func.count()).select_from(HabitCheck)) == 1


def test_uncheck_then_recheck_revives_the_same_row(client: TestClient, db_session: Session) -> None:
    habit = create(client)
    check(client, habit["id"], ago(0))
    row_id = db_session.scalars(select(HabitCheck.id)).one()

    assert client.delete(f"/api/v1/habits/{habit['id']}/checks/{ago(0)}").status_code == 204
    assert client.get(f"/api/v1/habits/{habit['id']}/checks").json() == []
    # Unchecking again is a no-op, not an error.
    assert client.delete(f"/api/v1/habits/{habit['id']}/checks/{ago(0)}").status_code == 204

    assert check(client, habit["id"], ago(0), "skipped").json()["status"] == "skipped"
    db_session.expire_all()
    assert db_session.scalars(select(HabitCheck.id)).all() == [row_id]


def test_check_rules(client: TestClient) -> None:
    habit = create(client, started_on=ago(2))
    assert check(client, habit["id"], ago(-1)).status_code == 422  # future
    assert check(client, habit["id"], ago(3)).status_code == 422  # before started_on
    assert check(client, habit["id"], "not-a-date").status_code == 422
    assert check(client, habit["id"], ago(1), "maybe").status_code == 422
    client.patch(f"/api/v1/habits/{habit['id']}", json={"archived": True})
    assert check(client, habit["id"], ago(1)).status_code == 409


def test_list_checks_in_range(client: TestClient) -> None:
    habit = create(client, started_on=ago(5))
    for n in (5, 3, 1):
        check(client, habit["id"], ago(n))
    res = client.get(f"/api/v1/habits/{habit['id']}/checks", params={"from": ago(4), "to": ago(0)})
    assert [c["date"] for c in res.json()] == [ago(3), ago(1)]


def test_for_date_adds_the_day(client: TestClient) -> None:
    weekday = TODAY.isoweekday()
    other_day = weekday % 7 + 1
    on_today = create(client, name="Today", started_on=ago(7), schedule_days=[weekday])
    create(client, name="Not today", started_on=ago(7), schedule_days=[other_day])
    check(client, on_today["id"], ago(0))

    res = client.get("/api/v1/habits", params={"for_date": ago(0)}).json()
    days = {h["name"]: h["day"] for h in res}
    assert days["Today"] == {"date": ago(0), "scheduled": True, "status": "done"}
    assert days["Not today"] == {"date": ago(0), "scheduled": False, "status": None}
    assert client.get("/api/v1/habits").json()[0]["day"] is None


# --- stats + heatmap ---


def test_stats(client: TestClient) -> None:
    habit = create(client, started_on=ago(4))
    for n in (4, 3, 1, 0):  # ago(2) missed
        check(client, habit["id"], ago(n))
    stats = client.get(f"/api/v1/habits/{habit['id']}/stats").json()
    assert stats["as_of"] == TODAY.isoformat()
    assert (stats["current_streak"], stats["longest_streak"]) == (2, 2)
    assert (stats["missed_count"], stats["expected_count"]) == (1, 5)
    assert stats["completion_rate"] == pytest.approx(0.8)


def test_heatmap_defaults_to_the_last_year(client: TestClient) -> None:
    habit = create(client, started_on=ago(1))
    check(client, habit["id"], ago(0))
    res = client.get("/api/v1/habits/heatmap").json()
    assert (res["start"], res["end"]) == (ago(364), ago(0))
    assert len(res["days"]) == 365
    assert res["days"][-2:] == [
        {"date": ago(1), "scheduled": 1, "done": 0, "skipped": 0},
        {"date": ago(0), "scheduled": 1, "done": 1, "skipped": 0},
    ]


def test_heatmap_for_one_habit(client: TestClient) -> None:
    read = create(client, name="Read", started_on=ago(2))
    create(client, name="Run", started_on=ago(2))
    check(client, read["id"], ago(1), "skipped")
    res = client.get(
        "/api/v1/habits/heatmap",
        params={"habit_id": read["id"], "from": ago(1), "to": ago(1)},
    ).json()
    assert res["days"] == [{"date": ago(1), "scheduled": 1, "done": 0, "skipped": 1}]


@pytest.mark.parametrize(
    "params",
    [
        {"from": ago(0), "to": ago(1)},  # backwards
        {"from": ago(800), "to": ago(0)},  # too long
        {"habit_id": str(uuid.uuid4())},  # unknown habit → 404 (checked below)
    ],
)
def test_heatmap_rejects_bad_ranges(client: TestClient, params: dict[str, str]) -> None:
    res = client.get("/api/v1/habits/heatmap", params=params)
    assert res.status_code == (404 if "habit_id" in params else 422)


# --- user scoping (D2) ---


def test_users_never_see_each_others_habits(client: TestClient, other_client: TestClient) -> None:
    habit = create(client)
    url = f"/api/v1/habits/{habit['id']}"

    assert other_client.get("/api/v1/habits").json() == []
    assert other_client.get(url).status_code == 404
    assert other_client.patch(url, json={"name": "Mine now"}).status_code == 404
    assert other_client.delete(url).status_code == 404
    assert check(other_client, habit["id"], ago(0)).status_code == 404
    assert other_client.get(f"{url}/stats").status_code == 404
    heatmap = other_client.get("/api/v1/habits/heatmap", params={"habit_id": habit["id"]})
    assert heatmap.status_code == 404

    # And the owner's habit is untouched.
    assert client.get(url).json()["name"] == "Read"
