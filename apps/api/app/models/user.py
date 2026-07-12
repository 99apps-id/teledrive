from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_operator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drive_initialized: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_api_id_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_api_hash_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_session_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_login_phone_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_login_code_hash_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_login_session_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    server_files_config_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
