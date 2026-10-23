"""HTTP routers, mounted under /api/v1. Thin: validate → call a service → return a schema."""

from fastapi import APIRouter

from ontherecord.api import habits, health, me, notes, todos

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(habits.router)
api_router.include_router(todos.router)
api_router.include_router(notes.router)
