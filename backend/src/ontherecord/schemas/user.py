import uuid
from datetime import datetime
from typing import Annotated, Self
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, model_validator

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class UserRead(BaseModel):
    """The signed-in user. `apple_sub` stays server-side."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str
    timezone: str
    created_at: datetime


# Scanning the tz database takes a few ms, so do it once.
_ZONES = frozenset(available_timezones())


def _iana_zone(value: str) -> str:
    if value not in _ZONES:
        raise ValueError("unknown time zone, expected an IANA name like America/Chicago")
    return value


class UserUpdate(BaseModel):
    """Partial update: only fields present in the body change."""

    display_name: DisplayName | None = None
    timezone: Annotated[str, AfterValidator(_iana_zone)] | None = None

    @model_validator(mode="after")
    def _no_null(self) -> Self:
        nulled = {f for f in self.model_fields_set if getattr(self, f) is None}
        if nulled:
            raise ValueError(f"cannot be null: {', '.join(sorted(nulled))}")
        return self
