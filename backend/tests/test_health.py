from fastapi.testclient import TestClient

from tests.conftest import MakeApp


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_down(make_app: MakeApp) -> None:
    # Nothing listens on port 1: the query fails and health degrades instead of crashing.
    app = make_app(database_url="postgresql+psycopg://nobody@127.0.0.1:1/none?connect_timeout=1")
    with TestClient(app) as c:
        res = c.get("/api/v1/health")
    assert res.status_code == 503
    assert res.json() == {"status": "degraded", "database": "unavailable"}


def test_openapi_lists_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/health", "/api/v1/me"} <= paths.keys()
