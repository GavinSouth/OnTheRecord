"""FastAPI app factory.

Run locally: `uv run uvicorn --factory ontherecord.main:create_app --reload`
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ontherecord import __version__
from ontherecord.api import api_router
from ontherecord.api.auth import dev_router
from ontherecord.config import Settings, get_settings
from ontherecord.db import make_engine, make_session_factory
from ontherecord.services.apple import AppleVerifier, apple_key_lookup
from ontherecord.services.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    UnauthorizedError,
)

ERROR_STATUS = {
    UnauthorizedError: status.HTTP_401_UNAUTHORIZED,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app. Tests pass their own settings; the server reads the environment."""
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="OnTheRecord", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    # Tests swap this for a verifier that trusts a locally generated key.
    app.state.apple_verifier = AppleVerifier(settings.apple_client_ids, apple_key_lookup())
    app.include_router(api_router)
    if settings.env != "prod":
        app.include_router(dev_router, prefix="/api/v1")

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        # Same {"detail": ...} shape FastAPI uses for its own errors.
        # RFC 9110: a 401 says which scheme to use.
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, UnauthorizedError) else None
        return JSONResponse(
            {"detail": exc.detail}, status_code=ERROR_STATUS[type(exc)], headers=headers
        )

    return app


def run() -> None:
    """`uv run ontherecord`: the dev server with auto-reload on http://127.0.0.1:8000."""
    import uvicorn

    uvicorn.run("ontherecord.main:create_app", factory=True, reload=True)
