"""Todo lists, items and their history. Every item mutation goes through this
module and writes its `TodoEvent` in the same transaction (D9)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select, update
from sqlalchemy.orm import Session

from ontherecord.models import TodoEvent, TodoEventType, TodoItem, TodoList, User
from ontherecord.schemas.todo import TodoItemCreate, TodoItemUpdate, TodoListCreate, TodoListUpdate
from ontherecord.services.clock import user_zone
from ontherecord.services.errors import ConflictError, NotFoundError

# --- helpers ---


def _end_position(session: Session, column: Any, *where: ColumnElement[bool]) -> float:
    last = session.scalar(select(func.max(column)).where(*where))
    return (last or 0.0) + 1.0


def _json(value: Any) -> Any:
    """Event data is JSONB: dates become ISO strings."""
    return value.isoformat() if isinstance(value, date) else value


def _log(
    session: Session, item: TodoItem, type: TodoEventType, data: dict[str, Any] | None = None
) -> None:
    session.add(TodoEvent(user_id=item.user_id, item_id=item.id, type=type, data=data or {}))


# --- lists ---


def _live_lists(user: User) -> Select[TodoList]:
    return select(TodoList).where(TodoList.user_id == user.id, TodoList.deleted_at.is_(None))


def list_lists(session: Session, user: User) -> list[tuple[TodoList, int]]:
    """All live lists, flat (the client builds the tree from `parent_id`), with
    each list's open item count."""
    lists = session.scalars(_live_lists(user).order_by(TodoList.position, TodoList.created_at))
    counts: dict[uuid.UUID, int] = {
        list_id: count
        for list_id, count in session.execute(
            select(TodoItem.list_id, func.count())
            .where(
                TodoItem.user_id == user.id,
                TodoItem.deleted_at.is_(None),
                TodoItem.completed_at.is_(None),
            )
            .group_by(TodoItem.list_id)
        )
    }
    return [(todo_list, counts.get(todo_list.id, 0)) for todo_list in lists]


def get_list(session: Session, user: User, list_id: uuid.UUID) -> TodoList:
    todo_list = session.scalars(_live_lists(user).where(TodoList.id == list_id)).one_or_none()
    if todo_list is None:
        raise NotFoundError("List not found")
    return todo_list


def _sibling_end(session: Session, user: User, parent_id: uuid.UUID | None) -> float:
    return _end_position(
        session,
        TodoList.position,
        TodoList.user_id == user.id,
        TodoList.deleted_at.is_(None),
        TodoList.parent_id.is_(None) if parent_id is None else TodoList.parent_id == parent_id,
    )


def create_list(session: Session, user: User, data: TodoListCreate) -> TodoList:
    if data.id is not None and session.get(TodoList, data.id) is not None:
        raise ConflictError("A list with this id already exists")
    if data.parent_id is not None:
        get_list(session, user, data.parent_id)
    todo_list = TodoList(
        user_id=user.id,
        parent_id=data.parent_id,
        name=data.name,
        position=data.position
        if data.position is not None
        else _sibling_end(session, user, data.parent_id),
    )
    if data.id is not None:
        todo_list.id = data.id
    session.add(todo_list)
    session.commit()
    return todo_list


def _ensure_no_cycle(session: Session, todo_list: TodoList, new_parent_id: uuid.UUID) -> None:
    """Reject moving a list into itself or one of its own descendants: walk up from
    the new parent; if we meet the list being moved, it would loop."""
    ancestors = (
        select(TodoList.id, TodoList.parent_id)
        .where(TodoList.id == new_parent_id)
        .cte("ancestors", recursive=True)
    )
    ancestors = ancestors.union(
        select(TodoList.id, TodoList.parent_id).join(
            ancestors, TodoList.id == ancestors.c.parent_id
        )
    )
    if todo_list.id in session.scalars(select(ancestors.c.id)).all():
        raise ConflictError("A list can't be moved into itself or one of its sublists")


def update_list(
    session: Session, user: User, todo_list: TodoList, data: TodoListUpdate
) -> TodoList:
    changes = data.model_dump(exclude_unset=True)
    if "parent_id" in changes and changes["parent_id"] != todo_list.parent_id:
        new_parent_id = changes["parent_id"]
        if new_parent_id is not None:
            get_list(session, user, new_parent_id)
            _ensure_no_cycle(session, todo_list, new_parent_id)
        todo_list.parent_id = new_parent_id
        if "position" not in changes:
            todo_list.position = _sibling_end(session, user, new_parent_id)
    if "name" in changes:
        todo_list.name = changes["name"]
    if "position" in changes:
        todo_list.position = changes["position"]
    session.commit()
    return todo_list


def delete_list(session: Session, user: User, todo_list: TodoList) -> None:
    """Soft-delete the list, every sublist under it, and all their items (each item
    gets a `deleted` event)."""
    tree = select(TodoList.id).where(TodoList.id == todo_list.id).cte("tree", recursive=True)
    tree = tree.union(
        select(TodoList.id)
        .join(tree, TodoList.parent_id == tree.c.id)
        .where(TodoList.deleted_at.is_(None))
    )
    list_ids = session.scalars(select(tree.c.id)).all()
    now = datetime.now(UTC)
    items = session.scalars(
        select(TodoItem).where(TodoItem.list_id.in_(list_ids), TodoItem.deleted_at.is_(None))
    ).all()
    for item in items:
        item.deleted_at = now
        _log(session, item, TodoEventType.DELETED, {"via_list_id": str(todo_list.id)})
    session.execute(update(TodoList).where(TodoList.id.in_(list_ids)).values(deleted_at=now))
    session.commit()


# --- items ---


def get_item(
    session: Session, user: User, item_id: uuid.UUID, *, include_deleted: bool = False
) -> TodoItem:
    query = select(TodoItem).where(TodoItem.id == item_id, TodoItem.user_id == user.id)
    if not include_deleted:
        query = query.where(TodoItem.deleted_at.is_(None))
    item = session.scalars(query).one_or_none()
    if item is None:
        raise NotFoundError("Item not found")
    return item


def list_items(session: Session, todo_list: TodoList, completed: bool | None) -> Sequence[TodoItem]:
    """Open items in list order; completed ones newest-completed first."""
    query = select(TodoItem).where(TodoItem.list_id == todo_list.id, TodoItem.deleted_at.is_(None))
    if completed is True:
        query = query.where(TodoItem.completed_at.is_not(None)).order_by(
            TodoItem.completed_at.desc()
        )
    else:
        if completed is False:
            query = query.where(TodoItem.completed_at.is_(None))
        query = query.order_by(TodoItem.position, TodoItem.created_at)
    return session.scalars(query).all()


def _item_end(session: Session, list_id: uuid.UUID) -> float:
    return _end_position(
        session, TodoItem.position, TodoItem.list_id == list_id, TodoItem.deleted_at.is_(None)
    )


def create_item(
    session: Session, user: User, todo_list: TodoList, data: TodoItemCreate
) -> TodoItem:
    if data.id is not None and session.get(TodoItem, data.id) is not None:
        raise ConflictError("An item with this id already exists")
    item = TodoItem(
        user_id=user.id,
        list_id=todo_list.id,
        title=data.title,
        notes=data.notes,
        due_date=data.due_date,
        position=data.position if data.position is not None else _item_end(session, todo_list.id),
    )
    if data.id is not None:
        item.id = data.id
    session.add(item)
    session.flush()  # get the server-generated id for the event
    _log(session, item, TodoEventType.CREATED, {"title": item.title, "list_id": str(item.list_id)})
    session.commit()
    return item


def update_item(session: Session, user: User, item: TodoItem, data: TodoItemUpdate) -> TodoItem:
    """One PATCH can produce several events (edited + moved + completed). A pure
    reorder (`position` only) logs nothing: it's layout, not history."""
    changes = data.model_dump(exclude_unset=True)

    edited = {}
    for field in ("title", "notes", "due_date"):
        if field in changes and changes[field] != getattr(item, field):
            edited[field] = {"from": _json(getattr(item, field)), "to": _json(changes[field])}
            setattr(item, field, changes[field])
    if edited:
        _log(session, item, TodoEventType.EDITED, {"changes": edited})

    if "list_id" in changes and changes["list_id"] != item.list_id:
        target = get_list(session, user, changes["list_id"])
        _log(
            session,
            item,
            TodoEventType.MOVED,
            {"from_list_id": str(item.list_id), "to_list_id": str(target.id)},
        )
        item.list_id = target.id
        if "position" not in changes:
            item.position = _item_end(session, target.id)
    if "position" in changes:
        item.position = changes["position"]

    if "completed" in changes:
        if changes["completed"] and item.completed_at is None:
            item.completed_at = datetime.now(UTC)
            _log(session, item, TodoEventType.COMPLETED)
        elif not changes["completed"] and item.completed_at is not None:
            item.completed_at = None
            _log(session, item, TodoEventType.REOPENED)

    session.commit()
    return item


def delete_item(session: Session, item: TodoItem) -> None:
    item.deleted_at = datetime.now(UTC)
    _log(session, item, TodoEventType.DELETED)
    session.commit()


# --- history ---


def item_events(session: Session, item: TodoItem) -> Sequence[TodoEvent]:
    # UUIDv7 ids sort by creation time, so id order is chronological order.
    return session.scalars(
        select(TodoEvent).where(TodoEvent.item_id == item.id).order_by(TodoEvent.id)
    ).all()


def events_page(
    session: Session,
    user: User,
    *,
    start: date | None,
    end: date | None,
    after: uuid.UUID | None,
    limit: int,
) -> tuple[Sequence[TodoEvent], uuid.UUID | None]:
    """Cursor pagination over the user's whole history, oldest first. `start`/`end`
    are local days (inclusive). Returns (events, next_cursor)."""
    zone = user_zone(user)
    query = select(TodoEvent).where(TodoEvent.user_id == user.id)
    if start is not None:
        query = query.where(TodoEvent.occurred_at >= datetime.combine(start, time(), zone))
    if end is not None:
        next_day = datetime.combine(end + timedelta(days=1), time(), zone)
        query = query.where(TodoEvent.occurred_at < next_day)
    if after is not None:
        query = query.where(TodoEvent.id > after)
    rows = session.scalars(query.order_by(TodoEvent.id).limit(limit + 1)).all()
    if len(rows) > limit:
        return rows[:limit], rows[limit - 1].id
    return rows, None
