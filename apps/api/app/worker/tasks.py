from celery import Celery
import asyncio

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.repositories.drive_repository import DriveRepository
from app.services.local_file_storage import LocalFileStorage
from app.services.sync_service import FileSyncService
from app.services.telegram_private_channel import TelegramPrivateChannelStorage

celery_app = Celery(
    "teledrive",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


@celery_app.task(name="teledrive.health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="teledrive.sync_file")
def sync_file(
    item_id: str,
    user_id: str,
    telegram_session_encrypted: str | None = None,
    telegram_api_id_encrypted: str | None = None,
    telegram_api_hash_encrypted: str | None = None,
) -> dict[str, str | None]:
    return asyncio.run(
        _sync_file(
            item_id,
            user_id,
            telegram_session_encrypted,
            telegram_api_id_encrypted,
            telegram_api_hash_encrypted,
        )
    )


async def _sync_file(
    item_id: str,
    user_id: str,
    telegram_session_encrypted: str | None,
    telegram_api_id_encrypted: str | None,
    telegram_api_hash_encrypted: str | None,
) -> dict[str, str | None]:
    async with SessionLocal() as session:
        repository = DriveRepository(session, settings.teledrive_storage_channel, user_id)
        service = FileSyncService(
            repository,
            LocalFileStorage(),
            TelegramPrivateChannelStorage(
                telegram_session=decrypt_secret(telegram_session_encrypted),
                telegram_api_id=decrypt_secret(telegram_api_id_encrypted),
                telegram_api_hash=decrypt_secret(telegram_api_hash_encrypted),
            ),
        )
        item = await service.sync_file(item_id)
        return {
            "id": item.id,
            "sync_status": item.sync_status,
            "remote_id": item.storage.remote_id,
        }
