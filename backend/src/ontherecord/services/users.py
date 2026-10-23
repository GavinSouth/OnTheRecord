from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ontherecord.models import User
from ontherecord.schemas.user import UserUpdate

DEV_APPLE_SUB = "dev-local"


def get_or_create_dev_user(session: Session) -> User:
    """The local user `POST /auth/dev` signs in as (dev and test only).

    INSERT … ON CONFLICT DO NOTHING makes this safe when two first requests race.
    """
    session.execute(
        insert(User)
        .values(apple_sub=DEV_APPLE_SUB, display_name="Dev User")
        .on_conflict_do_nothing(index_elements=[User.apple_sub])
    )
    user = session.scalars(select(User).where(User.apple_sub == DEV_APPLE_SUB)).one()
    session.commit()
    return user


def update_user(session: Session, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    session.commit()
    return user
