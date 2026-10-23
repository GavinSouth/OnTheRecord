"""Sign in with Apple: verify the identity token the app gets from Apple (D11).

The token is a JWT signed by Apple (RS256). Trusting it means checking the
signature against Apple's published keys, that Apple issued it (`iss`), that it
was issued to *our* app (`aud`), that it hasn't expired, and that its nonce
matches the one our app generated for this sign-in (so a token can't be replayed).
"""

import hashlib
import hmac
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import jwt

from ontherecord.services.errors import UnauthorizedError

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

# Given the raw token, return the public key that signed it (looked up by its `kid`).
# Raises a jwt.PyJWTError when no key matches.
KeyLookup = Callable[[str], Any]


@dataclass(frozen=True)
class AppleIdentity:
    sub: str  # Apple's stable user id for our team
    email: str | None  # may be a private relay address; absent on some sign-ins


class AppleVerifier:
    def __init__(self, client_ids: Sequence[str], key_lookup: KeyLookup) -> None:
        self.client_ids = list(client_ids)
        self.key_lookup = key_lookup

    def verify(self, identity_token: str, nonce: str) -> AppleIdentity:
        """`nonce` is the raw value the app generated; Apple embeds its SHA-256 hex."""
        if not self.client_ids:
            raise UnauthorizedError("Sign in with Apple is not configured")
        try:
            claims = jwt.decode(
                identity_token,
                self.key_lookup(identity_token),
                algorithms=["RS256"],
                audience=self.client_ids,
                issuer=APPLE_ISSUER,
                options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid Apple identity token") from exc
        expected = hashlib.sha256(nonce.encode()).hexdigest()
        if not hmac.compare_digest(str(claims["nonce"]), expected):
            raise UnauthorizedError("Invalid Apple identity token")
        return AppleIdentity(sub=claims["sub"], email=claims.get("email"))


def apple_key_lookup() -> KeyLookup:
    """Fetches Apple's keys over HTTPS, caches them, and refetches on an unknown `kid`
    (Apple rotates keys)."""
    client = jwt.PyJWKClient(APPLE_KEYS_URL, cache_jwk_set=True, lifespan=3600, timeout=10)

    def lookup(token: str) -> Any:
        # Raises a PyJWTError on an unknown kid or when Apple is unreachable.
        return client.get_signing_key_from_jwt(token).key

    return lookup
