import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ontherecord.models import User
from tests.conftest import MakeApp


def test_dev_stub_creates_one_user(client: TestClient, db_session: Session) -> None:
    first = client.get("/api/v1/me")
    second = client.get("/api/v1/me")

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["display_name"] == "Dev User"
    assert "apple_sub" not in first.json()
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_ids_are_uuidv7(client: TestClient) -> None:
    user_id = uuid.UUID(client.get("/api/v1/me").json()["id"])
    assert user_id.version == 7


def test_dev_stub_refuses_in_prod(make_app: MakeApp) -> None:
    with TestClient(make_app(env="prod")) as c:
        res = c.get("/api/v1/me")
    assert res.status_code == 401
