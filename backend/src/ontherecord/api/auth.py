"""Sign-in, token refresh and logout (D11). These routes are the only ones that
don't need an access token."""

from fastapi import APIRouter, Request, status

from ontherecord.api.deps import SessionDep, SettingsDep
from ontherecord.schemas.auth import AppleSignIn, RefreshRequest, TokenResponse
from ontherecord.services import auth
from ontherecord.services.apple import AppleVerifier
from ontherecord.services.users import get_or_create_dev_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _response(pair: auth.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/apple")
def sign_in_with_apple(
    body: AppleSignIn, request: Request, session: SessionDep, settings: SettingsDep
) -> TokenResponse:
    """Exchange an Apple identity token for our tokens. Creates the user on first sign-in."""
    verifier: AppleVerifier = request.app.state.apple_verifier
    identity = verifier.verify(body.identity_token, body.nonce)
    return _response(auth.sign_in_with_apple(session, identity, body.display_name, settings))


@router.post("/refresh")
def refresh(body: RefreshRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    """Rotate the refresh token. Clients must not refresh twice in parallel with the
    same token: the second call looks like theft and signs the device out."""
    return _response(auth.refresh(session, body.refresh_token, settings))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, session: SessionDep) -> None:
    """Revoke this device's session. Access tokens already issued expire on their own."""
    auth.logout(session, body.refresh_token)


# Mounted only outside prod (see main.py), so it isn't even in the prod OpenAPI spec.
dev_router = APIRouter(prefix="/auth", tags=["auth"])


@dev_router.post("/dev")
def dev_sign_in(session: SessionDep, settings: SettingsDep) -> TokenResponse:
    """Dev/test only: tokens for the local dev user, so `/docs` works without Apple."""
    return _response(auth.issue_tokens(session, get_or_create_dev_user(session), settings))
