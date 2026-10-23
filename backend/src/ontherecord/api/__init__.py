"""HTTP routers, mounted under /api/v1. Thin: validate → call a service → return a schema."""

from fastapi import APIRouter

from ontherecord.api import health, me

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(me.router)
