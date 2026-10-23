from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ontherecord.models import User

DEV_APPLE_SUB = "dev-local"


def get_or_create_dev_user(session: Session) -> User:
    """The single local user the dev stub signs everyone in as (until F2.5).

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
