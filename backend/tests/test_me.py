import uuid

from fastapi.testclient import TestClient


def test_me_returns_the_signed_in_user(client: TestClient) -> None:
    res = client.get("/api/v1/me")
    assert res.status_code == 200
    assert res.json()["display_name"] == "Test User"
    assert res.json()["timezone"] == "UTC"
    assert "apple_sub" not in res.json()


def test_ids_are_uuidv7(client: TestClient) -> None:
    user_id = uuid.UUID(client.get("/api/v1/me").json()["id"])
    assert user_id.version == 7


def test_update_me(client: TestClient) -> None:
    res = client.patch("/api/v1/me", json={"timezone": "America/Chicago"})
    assert res.status_code == 200
    assert res.json()["timezone"] == "America/Chicago"
    assert res.json()["display_name"] == "Test User"  # untouched

    res = client.patch("/api/v1/me", json={"display_name": "  Gavin  "})
    assert res.json()["display_name"] == "Gavin"
    assert client.get("/api/v1/me").json()["timezone"] == "America/Chicago"


def test_update_me_validates(client: TestClient) -> None:
    for body in (
        {"timezone": "Mars/Olympus"},
        {"timezone": "../../etc/passwd"},
        {"timezone": None},
        {"display_name": "x" * 101},
    ):
        assert client.patch("/api/v1/me", json=body).status_code == 422, body
