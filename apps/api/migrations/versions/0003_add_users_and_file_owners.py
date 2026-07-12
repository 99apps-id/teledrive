"""add users and file owners

Revision ID: 0003_add_users_and_file_owners
Revises: 0002_add_sync_fields
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_users_and_file_owners"
down_revision = "0002_add_sync_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("telegram_session_encrypted", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.add_column(
        "drive_items",
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default="local-dev-user"),
    )
    op.create_index("ix_drive_items_user_id", "drive_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_drive_items_user_id", table_name="drive_items")
    op.drop_column("drive_items", "user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
