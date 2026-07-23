"""add telegram api credentials

Revision ID: 0004_add_telegram_api_credentials
Revises: 0003_add_users_and_file_owners
Create Date: 2026-07-11 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_api_id_encrypted", sa.String(), nullable=True))
    op.add_column("users", sa.Column("telegram_api_hash_encrypted", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telegram_api_hash_encrypted")
    op.drop_column("users", "telegram_api_id_encrypted")
