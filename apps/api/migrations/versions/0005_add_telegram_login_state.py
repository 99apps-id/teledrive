"""add telegram login state

Revision ID: 0005_add_telegram_login_state
Revises: 0004_add_telegram_api_credentials
Create Date: 2026-07-11 15:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_login_phone_encrypted", sa.String(), nullable=True))
    op.add_column("users", sa.Column("telegram_login_code_hash_encrypted", sa.String(), nullable=True))
    op.add_column("users", sa.Column("telegram_login_session_encrypted", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telegram_login_session_encrypted")
    op.drop_column("users", "telegram_login_code_hash_encrypted")
    op.drop_column("users", "telegram_login_phone_encrypted")
