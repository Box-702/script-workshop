"""user model keys

Revision ID: c1f2a3b4d5e6
Revises: b8c4d2e7a901
Create Date: 2026-06-05 15:38:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f2a3b4d5e6"
down_revision: str | Sequence[str] | None = "b8c4d2e7a901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_model_keys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("default_model", sa.String(length=128), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_model_keys_user_id", "user_model_keys", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_user_model_keys_user_id", table_name="user_model_keys")
    op.drop_table("user_model_keys")
