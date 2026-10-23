"""Shared route dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ontherecord.config import Settings
from ontherecord.db import get_session
from ontherecord.models import User
from ontherecord.services.users import get_or_create_dev_user

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_current_user(session: SessionDep, settings: SettingsDep) -> User:
    """Dev-only stub (D11): everyone is the local dev user. Replaced by real
    token auth in F2.5. Refuses in prod so the stub can never ship open."""
    if settings.env == "prod":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is not configured")
    return get_or_create_dev_user(session)


CurrentUser = Annotated[User, Depends(get_current_user)]
