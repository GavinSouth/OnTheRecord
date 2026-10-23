"""create habits and habit checks

Revision ID: 0002
Revises: 0001
F2.2: habits + habit_checks (one row per habit per local day, D8).

Create Date: 2026-10-23 13:12:50.038634

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "habits",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "color",
            sa.Enum(
                "green",
                "blue",
                "orange",
                "plum",
                "gold",
                "slate",
                name="habit_color",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default="green",
            nullable=False,
        ),
        sa.Column("schedule_days", sa.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("position", sa.Double(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "cardinality(schedule_days) > 0 AND schedule_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]",
            name=op.f("ck_habits_schedule_days_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_habits_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habits")),
    )
    op.create_index(op.f("ix_habits_user_id"), "habits", ["user_id"], unique=False)
    op.create_table(
        "habit_checks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("habit_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "done",
                "skipped",
                name="check_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
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
            ["habit_id"],
            ["habits.id"],
            name=op.f("fk_habit_checks_habit_id_habits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_habit_checks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habit_checks")),
        sa.UniqueConstraint("habit_id", "date", name=op.f("uq_habit_checks_habit_id_date")),
    )
    op.create_index(
        "ix_habit_checks_user_id_date", "habit_checks", ["user_id", "date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_habit_checks_user_id_date", table_name="habit_checks")
    op.drop_table("habit_checks")
    op.drop_index(op.f("ix_habits_user_id"), table_name="habits")
    op.drop_table("habits")
