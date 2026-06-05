"""version metadata

Revision ID: b8c4d2e7a901
Revises: 71ad7f055dfc
Create Date: 2026-06-05 15:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c4d2e7a901"
down_revision: str | Sequence[str] | None = "71ad7f055dfc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column("owner_id", sa.String(length=64), nullable=False, server_default="local_user")
        )
        batch_op.add_column(sa.Column("current_version_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_projects_owner_id", ["owner_id"], unique=False)

    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.add_column(sa.Column("parent_version_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(length=32),
                nullable=False,
                server_default="generation",
            )
        )
        batch_op.add_column(sa.Column("label", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))

    connection = op.get_bind()
    latest_versions = connection.execute(
        sa.text(
            """
            SELECT project_id, id
            FROM script_versions AS sv
            WHERE created_at = (
                SELECT MAX(created_at)
                FROM script_versions
                WHERE project_id = sv.project_id
            )
            """
        )
    ).fetchall()
    for project_id, version_id in latest_versions:
        connection.execute(
            sa.text("UPDATE projects SET current_version_id = :version_id WHERE id = :project_id"),
            {"version_id": version_id, "project_id": project_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.drop_column("notes")
        batch_op.drop_column("label")
        batch_op.drop_column("source_type")
        batch_op.drop_column("parent_version_id")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_owner_id")
        batch_op.drop_column("current_version_id")
        batch_op.drop_column("owner_id")
