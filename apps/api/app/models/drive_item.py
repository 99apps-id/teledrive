from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DriveItemModel(Base):
    __tablename__ = "drive_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="local-dev-user")
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    storage_provider: Mapped[str] = mapped_column(
        String(64),
        default="telegram-private-channel",
    )
    storage_remote_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_channel_name: Mapped[str] = mapped_column(String(255))
    sync_status: Mapped[str] = mapped_column(String(64), default="local", index=True)
    sync_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
