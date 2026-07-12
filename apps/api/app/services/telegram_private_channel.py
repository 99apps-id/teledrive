from io import BytesIO
from pathlib import Path

from app.core.config import settings
from app.schemas.file import StorageStatus


class TelegramPrivateChannelStorage:
    """MTProto user-account storage boundary.

    TeleDrive uses Telegram only as private file storage. This service should
    create or reuse the user's private channel named "TeleDrive Storage" and
    upload files as documents. It must not expose chats, contacts, or messaging.
    """

    def __init__(
        self,
        telegram_session: str | None = None,
        telegram_api_id: str | None = None,
        telegram_api_hash: str | None = None,
    ) -> None:
        self.telegram_session = telegram_session
        self.telegram_api_id = telegram_api_id
        self.telegram_api_hash = telegram_api_hash

    def _credentials(self) -> tuple[str, str, str]:
        if self.telegram_api_id and self.telegram_api_hash and self.telegram_session:
            return self.telegram_api_id, self.telegram_api_hash, self.telegram_session
        if settings.telegram_api_id and settings.telegram_api_hash and self.telegram_session:
            return settings.telegram_api_id, settings.telegram_api_hash, self.telegram_session
        return settings.telegram_api_id, settings.telegram_api_hash, settings.telegram_session

    async def status(self) -> StorageStatus:
        api_id, api_hash, session = self._credentials()
        has_credentials = bool(api_id and api_hash and session)
        return StorageStatus(
            channel_name=settings.teledrive_storage_channel,
            connected=has_credentials,
            ready=has_credentials,
            details=(
                f'Configured to use private channel "{settings.teledrive_storage_channel}".'
                if has_credentials
                else "Waiting for TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_SESSION."
            ),
        )

    async def store_placeholder(
        self,
        *,
        name: str,
        size: int,
        mime_type: str | None,
    ) -> str | None:
        status = await self.status()
        if not status.ready:
            return None
        safe_name = "-".join(name.lower().split())
        return f"mtproto://{settings.teledrive_storage_channel}/{safe_name}-{size}"

    async def delete_object(self, remote_id: str | None) -> None:
        return None

    async def upload_document(
        self,
        *,
        path: Path,
        name: str,
        mime_type: str | None,
    ) -> str:
        status = await self.status()
        if not status.ready:
            raise RuntimeError(status.details)
        api_id, api_hash, session = self._credentials()

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.channels import CreateChannelRequest
        from telethon.tl.types import DocumentAttributeFilename

        client = TelegramClient(
            StringSession(session),
            int(api_id),
            api_hash,
        )

        async with client:
            channel = None
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                title = getattr(entity, "title", None)
                if title == settings.teledrive_storage_channel:
                    channel = entity
                    break

            if channel is None:
                created = await client(
                    CreateChannelRequest(
                        title=settings.teledrive_storage_channel,
                        about="Private TeleDrive storage channel",
                        megagroup=False,
                    )
                )
                channel = created.chats[0]

            message = await client.send_file(
                channel,
                file=str(path),
                caption=name[:1024],
                force_document=True,
                mime_type=mime_type or "application/octet-stream",
                attributes=[DocumentAttributeFilename(file_name=name)],
            )

            channel_id = getattr(channel, "id", "unknown")
            return f"telegram://{channel_id}/{message.id}"

    async def download_document(self, remote_id: str) -> bytes:
        if not remote_id.startswith("telegram://"):
            raise RuntimeError("Telegram document reference is invalid")
        try:
            message_id = int(remote_id.rsplit("/", 1)[1])
        except (IndexError, ValueError) as error:
            raise RuntimeError("Telegram message reference is invalid") from error

        api_id, api_hash, session = self._credentials()
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        try:
            await client.connect()
            channel = None
            async for dialog in client.iter_dialogs():
                if getattr(dialog.entity, "title", None) == settings.teledrive_storage_channel:
                    channel = dialog.entity
                    break
            if channel is None:
                raise RuntimeError("TeleDrive Storage channel was not found")
            message = await client.get_messages(channel, ids=message_id)
            if message is None or message.document is None:
                raise RuntimeError("Telegram document was not found")
            output = BytesIO()
            await client.download_media(message, file=output)
            return output.getvalue()
        finally:
            await client.disconnect()
