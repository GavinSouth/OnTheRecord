import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from ontherecord.api.deps import CurrentUser, SessionDep
from ontherecord.schemas.todo import (
    TodoEventPage,
    TodoEventRead,
    TodoItemCreate,
    TodoItemRead,
    TodoItemUpdate,
    TodoListCreate,
    TodoListRead,
    TodoListUpdate,
)
from ontherecord.services import todos as service

router = APIRouter(tags=["todos"])


# --- lists ---


@router.get("/lists")
def list_lists(session: SessionDep, user: CurrentUser) -> list[TodoListRead]:
    """Every list, flat. Build the tree from `parent_id` (null = top level)."""
    return [
        TodoListRead.model_validate(todo_list).model_copy(update={"open_count": count})
        for todo_list, count in service.list_lists(session, user)
    ]


@router.post("/lists", status_code=status.HTTP_201_CREATED)
def create_list(session: SessionDep, user: CurrentUser, body: TodoListCreate) -> TodoListRead:
    return TodoListRead.model_validate(service.create_list(session, user, body))


@router.patch("/lists/{list_id}")
def update_list(
    session: SessionDep, user: CurrentUser, list_id: uuid.UUID, body: TodoListUpdate
) -> TodoListRead:
    todo_list = service.get_list(session, user, list_id)
    return TodoListRead.model_validate(service.update_list(session, user, todo_list, body))


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(session: SessionDep, user: CurrentUser, list_id: uuid.UUID) -> None:
    """Deletes the list, its sublists, and all their items."""
    service.delete_list(session, user, service.get_list(session, user, list_id))


# --- items ---


@router.get("/lists/{list_id}/items")
def list_items(
    session: SessionDep,
    user: CurrentUser,
    list_id: uuid.UUID,
    completed: Annotated[bool | None, Query(description="Omit for both")] = None,
) -> list[TodoItemRead]:
    todo_list = service.get_list(session, user, list_id)
    return [
        TodoItemRead.model_validate(i) for i in service.list_items(session, todo_list, completed)
    ]


@router.post("/lists/{list_id}/items", status_code=status.HTTP_201_CREATED)
def create_item(
    session: SessionDep, user: CurrentUser, list_id: uuid.UUID, body: TodoItemCreate
) -> TodoItemRead:
    todo_list = service.get_list(session, user, list_id)
    return TodoItemRead.model_validate(service.create_item(session, user, todo_list, body))


@router.get("/items/{item_id}")
def read_item(session: SessionDep, user: CurrentUser, item_id: uuid.UUID) -> TodoItemRead:
    return TodoItemRead.model_validate(service.get_item(session, user, item_id))


@router.patch("/items/{item_id}")
def update_item(
    session: SessionDep, user: CurrentUser, item_id: uuid.UUID, body: TodoItemUpdate
) -> TodoItemRead:
    item = service.get_item(session, user, item_id)
    return TodoItemRead.model_validate(service.update_item(session, user, item, body))


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(session: SessionDep, user: CurrentUser, item_id: uuid.UUID) -> None:
    service.delete_item(session, service.get_item(session, user, item_id))


# --- history ---


@router.get("/items/{item_id}/events")
def item_events(session: SessionDep, user: CurrentUser, item_id: uuid.UUID) -> list[TodoEventRead]:
    """An item's full history, oldest first. Still available after the item is deleted."""
    item = service.get_item(session, user, item_id, include_deleted=True)
    return [TodoEventRead.model_validate(e) for e in service.item_events(session, item)]


@router.get("/todo-events")
def todo_events(
    session: SessionDep,
    user: CurrentUser,
    start: Annotated[date | None, Query(alias="from", description="Local day, inclusive")] = None,
    end: Annotated[date | None, Query(alias="to", description="Local day, inclusive")] = None,
    after: Annotated[
        uuid.UUID | None, Query(description="`next_cursor` of the previous page")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TodoEventPage:
    """All todo history, oldest first, for analytics. Cursor-paginated."""
    events, next_cursor = service.events_page(
        session, user, start=start, end=end, after=after, limit=limit
    )
    return TodoEventPage(
        events=[TodoEventRead.model_validate(e) for e in events], next_cursor=next_cursor
    )
