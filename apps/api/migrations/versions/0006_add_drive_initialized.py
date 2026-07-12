"""add drive initialization marker

Revision ID: 0006_add_drive_initialized
Revises: 0005_add_telegram_login_state
Create Date: 2026-07-11 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_drive_initialized"
down_revision = "0005_add_telegram_login_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "drive_initialized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "drive_initialized")
