"""create todo lists items and events

Revision ID: 0003
Revises: 0002
F2.3: nested todo lists, items, and the append-only todo_events log (D9).

Create Date: 2026-10-23 15:05:47.924987

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Defence in depth for D9: history rows can be inserted (and removed with their
# item or user), but never rewritten.
APPEND_ONLY_FUNCTION = """
CREATE FUNCTION todo_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'todo_events is append-only';
END;
$$
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER todo_events_no_update BEFORE UPDATE ON todo_events
FOR EACH ROW EXECUTE FUNCTION todo_events_append_only()
"""

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "todo_lists",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Double(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["todo_lists.id"],
            name=op.f("fk_todo_lists_parent_id_todo_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_todo_lists_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todo_lists")),
    )
    op.create_index(op.f("ix_todo_lists_parent_id"), "todo_lists", ["parent_id"], unique=False)
    op.create_index(op.f("ix_todo_lists_user_id"), "todo_lists", ["user_id"], unique=False)
    op.create_table(
        "todo_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Double(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["todo_lists.id"],
            name=op.f("fk_todo_items_list_id_todo_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_todo_items_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todo_items")),
    )
    op.create_index(op.f("ix_todo_items_list_id"), "todo_items", ["list_id"], unique=False)
    op.create_index(op.f("ix_todo_items_user_id"), "todo_items", ["user_id"], unique=False)
    op.create_table(
        "todo_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "created",
                "edited",
                "completed",
                "reopened",
                "moved",
                "deleted",
                "restored",
                name="todo_event_type",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["todo_items.id"],
            name=op.f("fk_todo_events_item_id_todo_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_todo_events_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todo_events")),
    )
    op.create_index(op.f("ix_todo_events_item_id"), "todo_events", ["item_id"], unique=False)
    op.create_index(
        "ix_todo_events_user_id_occurred_at",
        "todo_events",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER todo_events_no_update ON todo_events")
    op.execute("DROP FUNCTION todo_events_append_only()")
    op.drop_index("ix_todo_events_user_id_occurred_at", table_name="todo_events")
    op.drop_index(op.f("ix_todo_events_item_id"), table_name="todo_events")
    op.drop_table("todo_events")
    op.drop_index(op.f("ix_todo_items_user_id"), table_name="todo_items")
    op.drop_index(op.f("ix_todo_items_list_id"), table_name="todo_items")
    op.drop_table("todo_items")
    op.drop_index(op.f("ix_todo_lists_user_id"), table_name="todo_lists")
    op.drop_index(op.f("ix_todo_lists_parent_id"), table_name="todo_lists")
    op.drop_table("todo_lists")
