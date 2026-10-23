from fastapi import APIRouter

from ontherecord.api.deps import CurrentUser
from ontherecord.schemas.user import UserRead

router = APIRouter(tags=["me"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
