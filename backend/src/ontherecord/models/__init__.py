"""SQLAlchemy models. Import every model here so `Base.metadata` (and Alembic) sees it."""

from ontherecord.models.base import Base
from ontherecord.models.habit import CheckStatus, Habit, HabitCheck, HabitColor
from ontherecord.models.note import Note
from ontherecord.models.todo import TodoEvent, TodoEventType, TodoItem, TodoList
from ontherecord.models.user import User

__all__ = [
    "Base",
    "CheckStatus",
    "Habit",
    "HabitCheck",
    "HabitColor",
    "Note",
    "TodoEvent",
    "TodoEventType",
    "TodoItem",
    "TodoList",
    "User",
]
