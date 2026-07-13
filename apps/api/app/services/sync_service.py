from fastapi import HTTPException

from app.repositories.drive_repository import DriveRepository
from app.services.local_file_storage import LocalFileStorage
from app.services.telegram_private_channel import TelegramPrivateChannelStorage


class FileSyncService:
    def __init__(
        self,
        repository: DriveRepository,
        local_storage: LocalFileStorage,
        telegram_storage: TelegramPrivateChannelStorage,
    ) -> None:
        self.repository = repository
        self.local_storage = local_storage
        self.telegram_storage = telegram_storage

    async def sync_file(self, item_id: str):
        item = await self.repository.get(item_id)
        if item.kind != "file":
            raise HTTPException(status_code=400, detail="Only files can be synced")
        if item.storage.remote_id and item.storage.remote_id.startswith("telegram://"):
            return item

        status = await self.telegram_storage.status()
        if not status.ready:
            return await self.repository.mark_sync_waiting(item_id, status.details)

        await self.repository.mark_syncing(item_id)
        try:
            path = self.local_storage.resolve(item.storage.remote_id)
            remote_id = await self.telegram_storage.upload_document(
                path=path,
                name=item.name,
                mime_type=item.mime_type,
            )
            synced = await self.repository.mark_synced(item_id, remote_id)
            await self.local_storage.delete(item.storage.remote_id)
            return synced
        except Exception as error:
            return await self.repository.mark_sync_failed(item_id, str(error))
