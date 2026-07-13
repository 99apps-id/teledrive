from collections.abc import AsyncIterator
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
        return "", "", ""

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

    def _message_id(self, remote_id: str) -> int:
        if not remote_id.startswith("telegram://"):
            raise RuntimeError("Telegram document reference is invalid")
        try:
            return int(remote_id.rsplit("/", 1)[1])
        except (IndexError, ValueError) as error:
            raise RuntimeError("Telegram message reference is invalid") from error

    def _parse_remote_id(self, remote_id: str) -> tuple[int, int]:
        body = remote_id.removeprefix("telegram://")
        channel_id_str, message_id_str = body.rsplit("/", 1)
        return int(channel_id_str), int(message_id_str)

    async def _resolve_channel_entity(self, client, remote_id: str | None = None):
        if remote_id and remote_id.startswith("telegram://"):
            channel_id, _ = self._parse_remote_id(remote_id)
            candidates = [channel_id]
            if channel_id > 0:
                candidates.append(int(f"-100{channel_id}"))
            for candidate in candidates:
                try:
                    return await client.get_entity(candidate)
                except Exception:
                    continue

        async for dialog in client.iter_dialogs():
            title = getattr(dialog.entity, "title", None) or dialog.name
            if title == settings.teledrive_storage_channel:
                return dialog.entity
        raise RuntimeError("TeleDrive Storage channel was not found")

    async def _channel_map(self, client) -> dict[int, object]:
        channels: dict[int, object] = {}
        async for dialog in client.iter_dialogs():
            title = getattr(dialog.entity, "title", None) or dialog.name
            if title != settings.teledrive_storage_channel:
                continue
            channel_id = getattr(dialog.entity, "id", None)
            if channel_id is None:
                continue
            channels[channel_id] = dialog.entity
            if channel_id > 0:
                channels[int(f"-100{channel_id}")] = dialog.entity
        return channels

    def _channel_for_remote_id(self, channel_map: dict[int, object], remote_id: str):
        channel_id, _ = self._parse_remote_id(remote_id)
        channel = channel_map.get(channel_id)
        if channel is not None:
            return channel
        if channel_id > 0:
            return channel_map.get(int(f"-100{channel_id}"))
        return None

    async def delete_remote_ids(self, remote_ids: list[str | None]) -> list[str]:
        targets = [remote_id for remote_id in remote_ids if remote_id and remote_id.startswith("telegram://")]
        if not targets:
            return []

        api_id, api_hash, session = self._credentials()
        if not api_id or not api_hash or not session:
            return ["Telegram credentials are required to delete documents from storage"]

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        errors: list[str] = []
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        async with client:
            channel_map = await self._channel_map(client)
            for remote_id in targets:
                try:
                    channel = self._channel_for_remote_id(channel_map, remote_id)
                    if channel is None:
                        channel = await self._resolve_channel_entity(client, remote_id)
                    _, message_id = self._parse_remote_id(remote_id)
                    await client.delete_messages(channel, [message_id], revoke=True)
                    remaining = await client.get_messages(channel, ids=message_id)
                    if remaining is not None:
                        errors.append(f"{remote_id}: message still exists after delete")
                except Exception as error:
                    errors.append(f"{remote_id}: {error}")
        return errors

    async def filter_existing_remote_ids(self, remote_ids: list[str | None]) -> set[str]:
        targets = [remote_id for remote_id in remote_ids if remote_id and remote_id.startswith("telegram://")]
        if not targets:
            return set()

        api_id, api_hash, session = self._credentials()
        if not api_id or not api_hash or not session:
            return set(targets)

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        existing: set[str] = set()
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        async with client:
            channel_map = await self._channel_map(client)
            for remote_id in targets:
                try:
                    channel = self._channel_for_remote_id(channel_map, remote_id)
                    if channel is None:
                        channel = await self._resolve_channel_entity(client, remote_id)
                    _, message_id = self._parse_remote_id(remote_id)
                    message = await client.get_messages(channel, ids=message_id)
                    if message is not None:
                        existing.add(remote_id)
                except Exception:
                    continue
        return existing

    async def delete_object(self, remote_id: str | None) -> None:
        if not remote_id or remote_id.startswith("local://"):
            return
        errors = await self.delete_remote_ids([remote_id])
        if errors:
            raise RuntimeError(errors[0])

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

    async def purge_documents(self, *, keep_remote_ids: set[str] | None = None) -> int:
        keep = keep_remote_ids or set()
        to_delete = [
            document.get("remote_id")
            for document in await self.list_documents()
            if isinstance(document.get("remote_id"), str) and document["remote_id"] not in keep
        ]
        errors = await self.delete_remote_ids(to_delete)
        return len(to_delete) - len(errors)

    async def _document_message(self, remote_id: str):
        message_id = self._message_id(remote_id)
        api_id, api_hash, session = self._credentials()
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        await client.connect()
        try:
            channel = await self._resolve_channel_entity(client, remote_id)
            message = await client.get_messages(channel, ids=message_id)
            if message is None or message.document is None:
                raise RuntimeError("Telegram document was not found")
            return client, message
        except Exception:
            await client.disconnect()
            raise

    async def download_document(self, remote_id: str) -> bytes:
        client, message = await self._document_message(remote_id)
        try:
            output = BytesIO()
            await client.download_media(message, file=output)
            return output.getvalue()
        finally:
            await client.disconnect()

    async def download_document_to_path(self, remote_id: str, target: Path) -> None:
        client, message = await self._document_message(remote_id)
        try:
            await client.download_media(message, file=str(target))
        finally:
            await client.disconnect()

    async def download_document_stream(self, remote_id: str) -> AsyncIterator[bytes]:
        client, message = await self._document_message(remote_id)
        try:
            async for chunk in client.iter_download(message.media, request_size=512 * 1024):
                yield chunk
        finally:
            await client.disconnect()

    async def list_documents(self) -> list[dict[str, str | int | None]]:
        api_id, api_hash, session = self._credentials()
        if not api_id or not api_hash or not session:
            raise RuntimeError("Telegram credentials are required to import documents")

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        try:
            await client.connect()
            channel = await self._resolve_channel_entity(client)
            channel_id = getattr(channel, "id", "unknown")
            documents: list[dict[str, str | int | None]] = []
            async for message in client.iter_messages(channel):
                document = getattr(message, "document", None)
                if document is None:
                    continue
                attributes = getattr(document, "attributes", [])
                name = next(
                    (getattr(attribute, "file_name", None) for attribute in attributes if getattr(attribute, "file_name", None)),
                    None,
                )
                documents.append(
                    {
                        "remote_id": f"telegram://{channel_id}/{message.id}",
                        "name": name or f"telegram-document-{message.id}",
                        "size": getattr(document, "size", 0),
                        "mime_type": getattr(document, "mime_type", None),
                    }
                )
            return documents
        finally:
            await client.disconnect()
