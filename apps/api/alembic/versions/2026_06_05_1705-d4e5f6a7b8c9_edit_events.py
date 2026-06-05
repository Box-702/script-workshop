"""edit events

Revision ID: d4e5f6a7b8c9
Revises: c1f2a3b4d5e6
Create Date: 2026-06-05 17:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c1f2a3b4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "edit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("edit_type", sa.String(length=64), nullable=False),
        sa.Column("target_path", sa.String(length=255), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("patch", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["script_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edit_events_actor_id", "edit_events", ["actor_id"])
    op.create_index("ix_edit_events_project_id", "edit_events", ["project_id"])
    op.create_index("ix_edit_events_version_id", "edit_events", ["version_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_edit_events_version_id", table_name="edit_events")
    op.drop_index("ix_edit_events_project_id", table_name="edit_events")
    op.drop_index("ix_edit_events_actor_id", table_name="edit_events")
    op.drop_table("edit_events")
