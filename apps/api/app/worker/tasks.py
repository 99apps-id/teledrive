from celery import Celery
import asyncio

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.user import UserModel
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
) -> dict[str, str | None]:
    return asyncio.run(_sync_file(item_id, user_id))


async def _sync_file(
    item_id: str,
    user_id: str,
) -> dict[str, str | None]:
    async with SessionLocal() as session:
        user = await session.get(UserModel, user_id)
        if user is None:
            return {"id": item_id, "sync_status": "failed", "remote_id": None}
        repository = DriveRepository(session, settings.teledrive_storage_channel, user_id)
        service = FileSyncService(
            repository,
            LocalFileStorage(),
            TelegramPrivateChannelStorage(
                telegram_session=decrypt_secret(user.telegram_session_encrypted),
                telegram_api_id=decrypt_secret(user.telegram_api_id_encrypted),
                telegram_api_hash=decrypt_secret(user.telegram_api_hash_encrypted),
            ),
        )
        item = await service.sync_file(item_id)
        return {
            "id": item.id,
            "sync_status": item.sync_status,
            "remote_id": item.storage.remote_id,
        }
