"""add sync fields

Revision ID: 0002_add_sync_fields
Revises: 0001_create_drive_items
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drive_items",
        sa.Column("sync_status", sa.String(length=64), nullable=False, server_default="local"),
    )
    op.add_column(
        "drive_items",
        sa.Column("sync_error", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_drive_items_sync_status", "drive_items", ["sync_status"])


def downgrade() -> None:
    op.drop_index("ix_drive_items_sync_status", table_name="drive_items")
    op.drop_column("drive_items", "sync_error")
    op.drop_column("drive_items", "sync_status")
