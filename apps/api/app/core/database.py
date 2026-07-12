from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app.models.drive_item import DriveItemModel
    from app.models.user import UserModel

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if connection.dialect.name == "sqlite":
            user_columns = await connection.execute(text("PRAGMA table_info(users)"))
            user_names = {row[1] for row in user_columns}
            if "telegram_api_id_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN telegram_api_id_encrypted VARCHAR")
                )
            if "telegram_api_hash_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN telegram_api_hash_encrypted VARCHAR")
                )
            if "telegram_login_phone_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN telegram_login_phone_encrypted VARCHAR")
                )
            if "telegram_login_code_hash_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN telegram_login_code_hash_encrypted VARCHAR")
                )
            if "telegram_login_session_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN telegram_login_session_encrypted VARCHAR")
                )
            if "drive_initialized" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN drive_initialized BOOLEAN NOT NULL DEFAULT 0")
                )
            if "server_files_config_encrypted" not in user_names:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN server_files_config_encrypted VARCHAR")
                )

            columns = await connection.execute(text("PRAGMA table_info(drive_items)"))
            names = {row[1] for row in columns}
            if "user_id" not in names:
                await connection.execute(
                    text("ALTER TABLE drive_items ADD COLUMN user_id VARCHAR(64) NOT NULL DEFAULT 'local-dev-user'")
                )
                await connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_drive_items_user_id ON drive_items (user_id)")
                )
            if "sync_status" not in names:
                await connection.execute(
                    text("ALTER TABLE drive_items ADD COLUMN sync_status VARCHAR(64) NOT NULL DEFAULT 'local'")
                )
                await connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_drive_items_sync_status ON drive_items (sync_status)")
                )
            if "sync_error" not in names:
                await connection.execute(
                    text("ALTER TABLE drive_items ADD COLUMN sync_error VARCHAR(1024)")
                )
            if "deleted_at" not in names:
                await connection.execute(
                    text("ALTER TABLE drive_items ADD COLUMN deleted_at DATETIME")
                )
        else:
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_api_id_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_api_hash_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_login_phone_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_login_code_hash_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_login_session_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS drive_initialized BOOLEAN NOT NULL DEFAULT FALSE")
            )
            await connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS server_files_config_encrypted VARCHAR")
            )
            await connection.execute(
                text("ALTER TABLE drive_items ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) NOT NULL DEFAULT 'local-dev-user'")
            )
            await connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_drive_items_user_id ON drive_items (user_id)")
            )
            await connection.execute(
                text("ALTER TABLE drive_items ADD COLUMN IF NOT EXISTS sync_status VARCHAR(64) NOT NULL DEFAULT 'local'")
            )
            await connection.execute(
                text("ALTER TABLE drive_items ADD COLUMN IF NOT EXISTS sync_error VARCHAR(1024)")
            )
            await connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_drive_items_sync_status ON drive_items (sync_status)")
            )
            await connection.execute(
                text("ALTER TABLE drive_items ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE")
            )


async def close_db() -> None:
    await engine.dispose()
