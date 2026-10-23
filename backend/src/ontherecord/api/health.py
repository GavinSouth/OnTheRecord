from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ontherecord.api.deps import SessionDep
from ontherecord.schemas.health import Health

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep, response: Response) -> Health:
    """Liveness + database reachability. 503 when the database is down, so a
    host's health check can tell "app up, DB down" apart from "all good"."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="degraded", database="unavailable")
    return Health(status="ok", database="ok")
