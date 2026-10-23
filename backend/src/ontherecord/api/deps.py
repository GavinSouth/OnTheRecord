"""Shared route dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ontherecord.config import Settings
from ontherecord.db import get_session
from ontherecord.models import User
from ontherecord.services.auth import read_access_token
from ontherecord.services.errors import UnauthorizedError

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]

# auto_error=False: a missing header goes through our UnauthorizedError (401 +
# WWW-Authenticate) like every other auth failure. Also adds "Authorize" to /docs.
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    """The user named by a valid `Authorization: Bearer <access token>` header."""
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    user = session.get(User, read_access_token(credentials.credentials, settings))
    if user is None:  # deleted since the token was issued
        raise UnauthorizedError("Invalid access token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
