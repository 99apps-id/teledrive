"""add operator and app settings

Revision ID: 0009_add_operator_and_app_settings
Revises: 0008_add_server_files_config
Create Date: 2026-07-12 02:48:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0009_add_operator_and_app_settings"
down_revision = "0008_add_server_files_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_operator", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("bool_value", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    # Existing single-user installations retain control after upgrading.
    op.execute(
        "UPDATE users SET is_operator = TRUE "
        "WHERE id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)"
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("users", "is_operator")
