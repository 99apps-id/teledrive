"""add trash state

Revision ID: 0007_add_trash_state
Revises: 0006_add_drive_initialized
Create Date: 2026-07-11 23:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_trash_state"
down_revision = "0006_add_drive_initialized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drive_items",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("drive_items", "deleted_at")
