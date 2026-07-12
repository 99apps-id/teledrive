from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drive_item import DriveItemModel
from app.schemas.file import DriveItem, StorageRef

_UNSET = object()


class DriveRepository:
    def __init__(self, session: AsyncSession, channel_name: str, user_id: str):
        self.session = session
        self.channel_name = channel_name
        self.user_id = user_id

    async def seed_if_empty(self) -> None:
        count = await self.session.scalar(
            select(func.count())
            .select_from(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
        )
        if count:
            return

        now = datetime.now(timezone.utc)
        inbox = DriveItemModel(
            id=str(uuid4()),
            user_id=self.user_id,
            kind="folder",
            name="Inbox",
            parent_id=None,
            size=0,
            mime_type=None,
            created_at=now,
            updated_at=now,
            storage_remote_id=None,
            storage_channel_name=self.channel_name,
        )
        self.session.add(inbox)
        await self.session.commit()

    async def list(self, parent_id: str | None = None) -> list[DriveItem]:
        result = await self.session.scalars(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.deleted_at.is_(None))
            .where(DriveItemModel.parent_id.is_(None) if parent_id is None else DriveItemModel.parent_id == parent_id)
            .order_by(DriveItemModel.kind != "folder", DriveItemModel.name)
        )
        return [self._to_schema(item) for item in result.all()]

    async def get(self, item_id: str) -> DriveItem:
        return self._to_schema(await self._get_model(item_id))

    async def create_folder(self, name: str, parent_id: str | None = None) -> DriveItem:
        clean_name = name.strip()
        self._assert_name(clean_name)
        await self._assert_parent(parent_id)

        item = DriveItemModel(
            id=str(uuid4()),
            user_id=self.user_id,
            kind="folder",
            name=clean_name,
            parent_id=parent_id,
            size=0,
            mime_type=None,
            storage_remote_id=None,
            storage_channel_name=self.channel_name,
            sync_status="local",
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def create_file(
        self,
        name: str,
        parent_id: str | None,
        size: int,
        mime_type: str | None,
        remote_id: str | None,
    ) -> DriveItem:
        clean_name = name.strip()
        self._assert_name(clean_name)
        await self._assert_parent(parent_id)

        item = DriveItemModel(
            id=str(uuid4()),
            user_id=self.user_id,
            kind="file",
            name=clean_name,
            parent_id=parent_id,
            size=size,
            mime_type=mime_type,
            storage_remote_id=remote_id,
            storage_channel_name=self.channel_name,
            sync_status="local" if remote_id and remote_id.startswith("local://") else "synced",
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def move_to_trash(self, item_id: str) -> DriveItem:
        item = await self._get_model(item_id)
        item.deleted_at = datetime.now(timezone.utc)
        item.updated_at = item.deleted_at
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def list_trash(self) -> list[DriveItem]:
        result = await self.session.scalars(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.deleted_at.is_not(None))
            .order_by(DriveItemModel.deleted_at.desc())
        )
        return [self._to_schema(item) for item in result.all()]

    async def restore(self, item_id: str) -> DriveItem:
        item = await self._get_model(item_id)
        if item.deleted_at is None:
            raise HTTPException(status_code=409, detail="Item is not in Trash Bin")
        if item.parent_id is not None:
            parent = await self.session.get(DriveItemModel, item.parent_id)
            if parent is None or parent.user_id != self.user_id or parent.deleted_at is not None:
                item.parent_id = None
        item.deleted_at = None
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def delete_permanently(self, item_id: str) -> list[DriveItem]:
        item = await self._get_model(item_id)
        deleted: list[DriveItem] = []

        async def delete_tree(node: DriveItemModel) -> None:
            if node.kind == "folder":
                children = await self.session.scalars(
                    select(DriveItemModel)
                    .where(DriveItemModel.user_id == self.user_id)
                    .where(DriveItemModel.parent_id == node.id)
                )
                for child in children.all():
                    await delete_tree(child)
            deleted.append(self._to_schema(node))
            await self.session.delete(node)

        await delete_tree(item)
        await self.session.commit()
        return deleted

    async def empty_trash(self) -> list[DriveItem]:
        trashed = await self.session.scalars(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.deleted_at.is_not(None))
        )
        deleted: list[DriveItem] = []
        seen: set[str] = set()

        async def delete_tree(node: DriveItemModel) -> None:
            if node.id in seen:
                return
            seen.add(node.id)
            children = await self.session.scalars(
                select(DriveItemModel)
                .where(DriveItemModel.user_id == self.user_id)
                .where(DriveItemModel.parent_id == node.id)
            )
            for child in children.all():
                await delete_tree(child)
            deleted.append(self._to_schema(node))
            await self.session.delete(node)

        for item in trashed.all():
            await delete_tree(item)
        await self.session.commit()
        return deleted

    async def update(
        self,
        item_id: str,
        *,
        name: str | None = None,
        parent_id: str | None | object = _UNSET,
    ) -> DriveItem:
        item = await self._get_model(item_id)
        if name is not None:
            clean_name = name.strip()
            self._assert_name(clean_name)
            item.name = clean_name
        if parent_id is not _UNSET:
            if parent_id == item_id:
                raise HTTPException(status_code=400, detail="Item cannot be its own parent")
            if parent_id is not None:
                await self._assert_parent(parent_id)
            if item.kind == "folder":
                if parent_id is not None:
                    await self._assert_not_descendant(item_id, parent_id)
            item.parent_id = parent_id
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def mark_syncing(self, item_id: str) -> DriveItem:
        item = await self._get_model(item_id)
        item.sync_status = "syncing"
        item.sync_error = None
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def mark_sync_waiting(self, item_id: str, message: str) -> DriveItem:
        item = await self._get_model(item_id)
        item.sync_status = "waiting_for_telegram_session"
        item.sync_error = message
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def mark_synced(self, item_id: str, remote_id: str) -> DriveItem:
        item = await self._get_model(item_id)
        item.storage_remote_id = remote_id
        item.sync_status = "synced"
        item.sync_error = None
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def mark_sync_failed(self, item_id: str, message: str) -> DriveItem:
        item = await self._get_model(item_id)
        item.sync_status = "failed"
        item.sync_error = message[:1024]
        item.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def _get_model(self, item_id: str) -> DriveItemModel:
        item = await self.session.get(DriveItemModel, item_id)
        if item is None or item.user_id != self.user_id:
            raise HTTPException(status_code=404, detail="Drive item not found")
        return item

    async def _assert_parent(self, parent_id: str | None) -> None:
        if parent_id is None:
            return
        parent = await self._get_model(parent_id)
        if parent.kind != "folder":
            raise HTTPException(status_code=400, detail="Parent must be a folder")

    async def _assert_not_descendant(self, item_id: str, parent_id: str) -> None:
        current_id: str | None = parent_id
        visited: set[str] = set()
        while current_id is not None:
            if current_id == item_id:
                raise HTTPException(
                    status_code=400,
                    detail="Folder cannot be moved inside itself",
                )
            if current_id in visited:
                raise HTTPException(status_code=409, detail="Folder hierarchy contains a cycle")
            visited.add(current_id)
            current = await self._get_model(current_id)
            current_id = current.parent_id

    def _assert_name(self, name: str) -> None:
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")

    def _to_schema(self, item: DriveItemModel) -> DriveItem:
        return DriveItem(
            id=item.id,
            kind=item.kind,  # type: ignore[arg-type]
            name=item.name,
            parent_id=item.parent_id,
            size=item.size,
            mime_type=item.mime_type,
            created_at=item.created_at,
            updated_at=item.updated_at,
            storage=StorageRef(
                provider="telegram-private-channel",
                remote_id=item.storage_remote_id,
                channel_name=item.storage_channel_name,
            ),
            sync_status=item.sync_status,
            sync_error=item.sync_error,
        )
