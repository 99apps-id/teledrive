"""add server files config

Revision ID: 0008_add_server_files_config
Revises: 0007_add_trash_state
Create Date: 2026-07-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("server_files_config_encrypted", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "server_files_config_encrypted")
