"""Server-issued tokens (D11).

- **Access token**: a short-lived JWT (HS256, our secret). Stateless: checking it
  needs no database lookup for the token itself, so it can't be revoked early;
  the short lifetime bounds that.
- **Refresh token**: a long-lived random string, stored only as a SHA-256 hash.
  Every refresh rotates it. If a used token comes back, someone kept a copy, so
  the whole family (that device's session) is revoked and must sign in again.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ontherecord.config import Settings
from ontherecord.models import RefreshToken, User
from ontherecord.services.apple import AppleIdentity
from ontherecord.services.errors import UnauthorizedError

ISSUER = "ontherecord"
ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # access token lifetime, seconds


def _hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()


def issue_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "sub": str(user_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def read_access_token(token: str, settings: Settings) -> uuid.UUID:
    """The user id in a valid access token."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],  # pinned: never let the token pick its algorithm
            issuer=ISSUER,
            options={"require": ["iss", "sub", "exp", "typ"]},
        )
        if claims["typ"] != "access":
            raise UnauthorizedError("Invalid access token")
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError("Invalid access token") from exc


def issue_tokens(
    session: Session, user: User, settings: Settings, family_id: uuid.UUID | None = None
) -> TokenPair:
    """A new access + refresh pair. Without `family_id`, starts a new session (sign-in)."""
    raw = secrets.token_urlsafe(32)  # 256 bits: a fast hash is enough, no bcrypt needed
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=_hash(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    session.commit()
    return TokenPair(
        access_token=issue_access_token(user.id, settings),
        refresh_token=raw,
        expires_in=settings.access_token_minutes * 60,
    )


def sign_in_with_apple(
    session: Session, identity: AppleIdentity, display_name: str | None, settings: Settings
) -> TokenPair:
    """Find or create the user for a verified Apple identity, then start a session.

    Apple shares the user's name only on the very first sign-in (the app passes it
    as `display_name`), so it's only used when creating the user.
    """
    session.execute(
        insert(User)
        .values(apple_sub=identity.sub, email=identity.email, display_name=display_name or "")
        .on_conflict_do_nothing(index_elements=[User.apple_sub])
    )
    user = session.scalars(select(User).where(User.apple_sub == identity.sub)).one()
    if identity.email and user.email != identity.email:
        user.email = identity.email
    return issue_tokens(session, user, settings)


def refresh(session: Session, raw: str, settings: Settings) -> TokenPair:
    """Rotate a refresh token. Reuse of a rotated token revokes its family."""
    now = datetime.now(UTC)
    # FOR UPDATE: two concurrent refreshes with the same token run one after the other,
    # so only one can rotate it (the second is treated as reuse).
    token = session.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw)).with_for_update()
    ).one_or_none()
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        raise UnauthorizedError("Invalid refresh token")
    if token.used_at is not None:
        _revoke_family(session, token.family_id, now)
        session.commit()
        raise UnauthorizedError("Invalid refresh token")
    user = session.get(User, token.user_id)
    if user is None:
        raise UnauthorizedError("Invalid refresh token")
    token.used_at = now
    return issue_tokens(session, user, settings, family_id=token.family_id)


def logout(session: Session, raw: str) -> None:
    """End the session the refresh token belongs to. Unknown tokens are ignored, so
    logout is idempotent and reveals nothing."""
    token = session.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw))
    ).one_or_none()
    if token is not None:
        _revoke_family(session, token.family_id, datetime.now(UTC))
        session.commit()


def _revoke_family(session: Session, family_id: uuid.UUID, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
