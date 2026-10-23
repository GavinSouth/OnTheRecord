"""What "today" means for a user: their local calendar day (D8)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ontherecord.models import User


def user_zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_date(user: User, moment: datetime) -> date:
    return moment.astimezone(user_zone(user)).date()


def user_today(user: User) -> date:
    return local_date(user, datetime.now(UTC))
