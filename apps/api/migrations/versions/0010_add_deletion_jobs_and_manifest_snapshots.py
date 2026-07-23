"""add durable deletion jobs and encrypted manifests

Revision ID: 0010_add_deletion_jobs_and_manifest_snapshots
Revises: 0009_add_operator_and_app_settings
Create Date: 2026-07-12 18:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deletion_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("remote_id", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "remote_id", name="uq_deletion_jobs_user_remote"),
    )
    op.create_index("ix_deletion_jobs_user_id", "deletion_jobs", ["user_id"])
    op.create_index("ix_deletion_jobs_status", "deletion_jobs", ["status"])
    op.create_index("ix_deletion_jobs_next_attempt_at", "deletion_jobs", ["next_attempt_at"])
    op.create_table(
        "manifest_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("remote_id", sa.String(length=512), nullable=True),
        sa.Column("content_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manifest_snapshots_user_id", "manifest_snapshots", ["user_id"])
    op.create_index("ix_manifest_snapshots_created_at", "manifest_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_table("manifest_snapshots")
    op.drop_table("deletion_jobs")
