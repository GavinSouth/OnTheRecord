from fastapi import APIRouter

from ontherecord.api.deps import CurrentUser, SessionDep
from ontherecord.schemas.user import UserRead, UserUpdate
from ontherecord.services.users import update_user

router = APIRouter(tags=["me"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me")
def update_me(body: UserUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    """Display name and time zone. The time zone defines "today" for habits (D8)."""
    return UserRead.model_validate(update_user(session, user, body))
