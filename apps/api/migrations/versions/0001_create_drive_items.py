"""create drive items

Revision ID: 0001_create_drive_items
Revises:
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_drive_items"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drive_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("parent_id", sa.String(length=64), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_provider", sa.String(length=64), nullable=False),
        sa.Column("storage_remote_id", sa.String(length=512), nullable=True),
        sa.Column("storage_channel_name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drive_items_kind", "drive_items", ["kind"])
    op.create_index("ix_drive_items_name", "drive_items", ["name"])
    op.create_index("ix_drive_items_parent_id", "drive_items", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_drive_items_parent_id", table_name="drive_items")
    op.drop_index("ix_drive_items_name", table_name="drive_items")
    op.drop_index("ix_drive_items_kind", table_name="drive_items")
    op.drop_table("drive_items")
