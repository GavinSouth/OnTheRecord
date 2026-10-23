"""Auth (D11). Apple is replaced by a locally generated RSA key: the verifier gets
the same checks as in prod (signature, iss, aud, exp, nonce), just a different key."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ontherecord.db import get_session
from ontherecord.models import RefreshToken, User
from ontherecord.services.apple import APPLE_ISSUER, AppleVerifier
from tests.conftest import TEST_APPLE_CLIENT_ID, TEST_JWT_SECRET, MakeApp

NONCE = "raw-nonce-from-the-app"


@pytest.fixture(scope="session")
def apple_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def anon_client(
    make_app: MakeApp, db_session: Session, apple_key: rsa.RSAPrivateKey
) -> Iterator[TestClient]:
    """No credentials, and an Apple verifier that trusts `apple_key`."""
    app = make_app()
    app.dependency_overrides[get_session] = lambda: db_session
    public_key = apple_key.public_key()
    app.state.apple_verifier = AppleVerifier([TEST_APPLE_CLIENT_ID], lambda _: public_key)
    with TestClient(app) as c:
        yield c


def apple_token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": APPLE_ISSUER,
        "aud": TEST_APPLE_CLIENT_ID,
        "sub": "001234.apple-user",
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "nonce": hashlib.sha256(NONCE.encode()).hexdigest(),
        "email": "someone@privaterelay.appleid.com",
    } | overrides
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


def sign_in(c: TestClient, token: str, **body: Any) -> Any:
    return c.post("/api/v1/auth/apple", json={"identity_token": token, "nonce": NONCE} | body)


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# Sign in with Apple


def test_sign_in_creates_user_then_reuses_it(
    anon_client: TestClient, apple_key: rsa.RSAPrivateKey, db_session: Session
) -> None:
    first = sign_in(anon_client, apple_token(apple_key), display_name="Gavin")
    assert first.status_code == 200
    tokens = first.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 15 * 60

    me = anon_client.get("/api/v1/me", headers=bearer(tokens["access_token"])).json()
    assert me["display_name"] == "Gavin"
    assert me["email"] == "someone@privaterelay.appleid.com"

    # Later sign-ins: Apple sends no name and may omit the email; neither is wiped.
    again = sign_in(anon_client, apple_token(apple_key, email=None))
    me_again = anon_client.get("/api/v1/me", headers=bearer(again.json()["access_token"])).json()
    assert me_again["id"] == me["id"]
    assert me_again["display_name"] == "Gavin"
    assert me_again["email"] == "someone@privaterelay.appleid.com"
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "com.someone-else.app"},
        {"iss": "https://evil.example.com"},
        {"exp": datetime.now(UTC) - timedelta(minutes=5)},
        {"nonce": hashlib.sha256(b"another nonce").hexdigest()},
        {"nonce": None},
        {"sub": None},
    ],
    ids=["audience", "issuer", "expired", "nonce-mismatch", "nonce-missing", "sub-missing"],
)
def test_sign_in_rejects_bad_apple_tokens(
    anon_client: TestClient, apple_key: rsa.RSAPrivateKey, overrides: dict[str, Any]
) -> None:
    res = sign_in(anon_client, apple_token(apple_key, **overrides))
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"


def test_sign_in_rejects_token_signed_by_another_key(anon_client: TestClient) -> None:
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert sign_in(anon_client, apple_token(impostor)).status_code == 401


def test_sign_in_rejects_garbage(anon_client: TestClient) -> None:
    assert sign_in(anon_client, "not-a-jwt").status_code == 401


# Access tokens


def test_protected_routes_need_a_token(anon_client: TestClient) -> None:
    for path in ("/api/v1/me", "/api/v1/habits", "/api/v1/lists", "/api/v1/notes"):
        res = anon_client.get(path)
        assert res.status_code == 401, path
        assert res.headers["www-authenticate"] == "Bearer"


def test_health_needs_no_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/v1/health").status_code == 200


def _access(sub: str, secret: str = TEST_JWT_SECRET, **overrides: Any) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "ontherecord",
        "sub": sub,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(claims | overrides, secret, algorithm="HS256")


def test_rejects_bad_access_tokens(client: TestClient, anon_client: TestClient) -> None:
    user_id = client.get("/api/v1/me").json()["id"]
    assert anon_client.get("/api/v1/me", headers=bearer(_access(user_id))).status_code == 200

    bad = [
        _access(user_id, secret="x" * 40),  # forged
        _access(user_id, exp=datetime.now(UTC) - timedelta(seconds=1)),  # expired
        _access(user_id, typ="refresh"),
        _access(user_id, iss="someone-else"),
        _access("not-a-uuid"),
        _access("01890000-0000-7000-8000-000000000000"),  # no such user
        jwt.encode({"sub": user_id, "typ": "access"}, "", algorithm="none"),  # alg=none attack
    ]
    for token in bad:
        assert anon_client.get("/api/v1/me", headers=bearer(token)).status_code == 401


# Refresh tokens


@pytest.fixture
def tokens(anon_client: TestClient, apple_key: rsa.RSAPrivateKey) -> dict[str, Any]:
    res = sign_in(anon_client, apple_token(apple_key))
    data: dict[str, Any] = res.json()
    return data


def refresh(c: TestClient, token: str) -> Any:
    return c.post("/api/v1/auth/refresh", json={"refresh_token": token})


def test_refresh_rotates(anon_client: TestClient, tokens: dict[str, Any]) -> None:
    res = refresh(anon_client, tokens["refresh_token"])
    assert res.status_code == 200
    new = res.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    assert anon_client.get("/api/v1/me", headers=bearer(new["access_token"])).status_code == 200
    assert refresh(anon_client, new["refresh_token"]).status_code == 200


def test_reusing_a_refresh_token_revokes_the_session(
    anon_client: TestClient, tokens: dict[str, Any]
) -> None:
    stolen = tokens["refresh_token"]
    rotated = refresh(anon_client, stolen).json()["refresh_token"]

    assert refresh(anon_client, stolen).status_code == 401  # replay detected
    assert refresh(anon_client, rotated).status_code == 401  # the whole family is gone


def test_reuse_only_revokes_that_device(
    anon_client: TestClient, apple_key: rsa.RSAPrivateKey, tokens: dict[str, Any]
) -> None:
    other_device = sign_in(anon_client, apple_token(apple_key)).json()["refresh_token"]
    refresh(anon_client, tokens["refresh_token"])
    refresh(anon_client, tokens["refresh_token"])
    assert refresh(anon_client, other_device).status_code == 200


def test_expired_refresh_token(
    anon_client: TestClient, tokens: dict[str, Any], db_session: Session
) -> None:
    db_session.execute(
        update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    assert refresh(anon_client, tokens["refresh_token"]).status_code == 401


def test_unknown_refresh_token(anon_client: TestClient) -> None:
    assert refresh(anon_client, "made-up").status_code == 401


def test_only_hashes_are_stored(tokens: dict[str, Any], db_session: Session) -> None:
    stored = db_session.scalars(select(RefreshToken.token_hash)).all()
    assert stored == [hashlib.sha256(tokens["refresh_token"].encode()).digest()]


# Logout


def test_logout_revokes_the_session(anon_client: TestClient, tokens: dict[str, Any]) -> None:
    body = {"refresh_token": tokens["refresh_token"]}
    assert anon_client.post("/api/v1/auth/logout", json=body).status_code == 204
    assert refresh(anon_client, tokens["refresh_token"]).status_code == 401
    # Idempotent, and an unknown token looks the same.
    assert anon_client.post("/api/v1/auth/logout", json=body).status_code == 204
    assert anon_client.post("/api/v1/auth/logout", json={"refresh_token": "x"}).status_code == 204


# Dev sign-in


def test_dev_sign_in(anon_client: TestClient) -> None:
    tokens = anon_client.post("/api/v1/auth/dev").json()
    me = anon_client.get("/api/v1/me", headers=bearer(tokens["access_token"])).json()
    assert me["display_name"] == "Dev User"
    assert refresh(anon_client, tokens["refresh_token"]).status_code == 200


def test_dev_sign_in_does_not_exist_in_prod(make_app: MakeApp) -> None:
    with TestClient(make_app(env="prod")) as c:
        assert c.post("/api/v1/auth/dev").status_code == 404
        assert "/api/v1/auth/dev" not in c.get("/openapi.json").json()["paths"]


def test_apple_sign_in_unconfigured(make_app: MakeApp, apple_key: rsa.RSAPrivateKey) -> None:
    with TestClient(make_app(apple_client_ids=[])) as c:
        assert sign_in(c, apple_token(apple_key)).status_code == 401
