from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
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

    async def get_or_create_folder(self, name: str, parent_id: str | None = None) -> DriveItem:
        existing = await self.session.scalar(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.kind == "folder")
            .where(DriveItemModel.name == name)
            .where(
                DriveItemModel.parent_id.is_(None)
                if parent_id is None
                else DriveItemModel.parent_id == parent_id
            )
            .where(DriveItemModel.deleted_at.is_(None))
            .order_by(DriveItemModel.created_at)
        )
        if existing is not None:
            return self._to_schema(existing)
        return await self.create_folder(name, parent_id)

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
            sync_status=(
                "synced"
                if remote_id and remote_id.startswith("telegram://")
                else "local"
                if remote_id and remote_id.startswith("local://")
                else "pending_upload"
            ),
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return self._to_schema(item)

    async def import_telegram_file(
        self,
        *,
        name: str,
        size: int,
        mime_type: str | None,
        remote_id: str,
        parent_id: str | None = None,
    ) -> DriveItem:
        existing = await self.session.scalar(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.storage_remote_id == remote_id)
        )
        if existing is not None:
            return self._to_schema(existing)
        return await self.create_file(name, parent_id, size, mime_type, remote_id)

    async def manifest_items(self) -> list[dict[str, object]]:
        result = await self.session.scalars(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .order_by(DriveItemModel.created_at, DriveItemModel.id)
        )
        return [
            {
                "id": item.id,
                "kind": item.kind,
                "name": item.name,
                "parent_id": item.parent_id,
                "size": item.size,
                "mime_type": item.mime_type,
                "storage_remote_id": item.storage_remote_id,
                "storage_channel_name": item.storage_channel_name,
                "sync_status": item.sync_status,
                "sync_error": item.sync_error,
                "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in result.all()
        ]

    async def restore_manifest_items(self, items: list[dict[str, object]]) -> int:
        restored = 0
        for raw in items:
            item_id = raw.get("id")
            kind = raw.get("kind")
            name = raw.get("name")
            if not isinstance(item_id, str) or kind not in {"file", "folder"} or not isinstance(name, str):
                continue
            current = await self.session.get(DriveItemModel, item_id)
            if current is not None:
                if current.user_id != self.user_id:
                    continue
                continue
            parent_id = raw.get("parent_id")
            remote_id = raw.get("storage_remote_id")
            channel = raw.get("storage_channel_name")
            item = DriveItemModel(
                id=item_id,
                user_id=self.user_id,
                kind=kind,
                name=name[:512],
                parent_id=parent_id if isinstance(parent_id, str) else None,
                size=raw.get("size") if isinstance(raw.get("size"), int) else 0,
                mime_type=raw.get("mime_type") if isinstance(raw.get("mime_type"), str) else None,
                storage_remote_id=remote_id if isinstance(remote_id, str) else None,
                storage_channel_name=channel if isinstance(channel, str) else self.channel_name,
                sync_status=raw.get("sync_status") if isinstance(raw.get("sync_status"), str) else "synced",
                sync_error=raw.get("sync_error") if isinstance(raw.get("sync_error"), str) else None,
            )
            self.session.add(item)
            restored += 1
        await self.session.commit()
        return restored

    async def _load_user_item_maps(
        self,
    ) -> tuple[dict[str, DriveItemModel], dict[str | None, list[DriveItemModel]]]:
        result = await self.session.scalars(
            select(DriveItemModel).where(DriveItemModel.user_id == self.user_id)
        )
        items = result.all()
        by_id = {item.id: item for item in items}
        by_parent: dict[str | None, list[DriveItemModel]] = {}
        for item in items:
            by_parent.setdefault(item.parent_id, []).append(item)
        return by_id, by_parent

    def _collect_subtree(
        self,
        root_id: str,
        by_id: dict[str, DriveItemModel],
        by_parent: dict[str | None, list[DriveItemModel]],
        seen: set[str],
    ) -> list[DriveItemModel]:
        if root_id in seen or root_id not in by_id:
            return []
        seen.add(root_id)
        collected: list[DriveItemModel] = []
        for child in by_parent.get(root_id, []):
            collected.extend(self._collect_subtree(child.id, by_id, by_parent, seen))
        collected.append(by_id[root_id])
        return collected

    async def _delete_collected_models(
        self,
        models: list[DriveItemModel],
        *,
        commit: bool,
    ) -> list[DriveItem]:
        deleted = [self._to_schema(model) for model in models]
        for model in models:
            await self.session.delete(model)
        if commit:
            await self.session.commit()
        return deleted

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

    async def delete_permanently(self, item_id: str, *, commit: bool = True) -> list[DriveItem]:
        await self._get_model(item_id)
        by_id, by_parent = await self._load_user_item_maps()
        seen: set[str] = set()
        models = self._collect_subtree(item_id, by_id, by_parent, seen)
        return await self._delete_collected_models(models, commit=commit)

    async def delete_permanently_many(self, item_ids: list[str], *, commit: bool = True) -> list[DriveItem]:
        by_id, by_parent = await self._load_user_item_maps()
        seen: set[str] = set()
        models: list[DriveItemModel] = []
        for item_id in item_ids:
            models.extend(self._collect_subtree(item_id, by_id, by_parent, seen))
        return await self._delete_collected_models(models, commit=commit)

    async def empty_trash(self, *, commit: bool = True) -> list[DriveItem]:
        trashed = await self.session.scalars(
            select(DriveItemModel)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.deleted_at.is_not(None))
        )
        trashed_roots = [item.id for item in trashed.all()]
        if not trashed_roots:
            return []
        by_id, by_parent = await self._load_user_item_maps()
        seen: set[str] = set()
        models: list[DriveItemModel] = []
        for root_id in trashed_roots:
            models.extend(self._collect_subtree(root_id, by_id, by_parent, seen))
        return await self._delete_collected_models(models, commit=commit)

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

    async def replace_file_content(
        self,
        item_id: str,
        *,
        remote_id: str,
        size: int,
        sync_status: str,
        sync_error: str | None = None,
        expected_revision: datetime | None = None,
    ) -> DriveItem:
        current = await self._get_model(item_id)
        if current.kind != "file":
            raise HTTPException(status_code=400, detail="Only files have editable content")
        if expected_revision is None:
            raise HTTPException(status_code=428, detail="A file revision is required to save edits")
        updated_at = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(DriveItemModel)
            .where(DriveItemModel.id == item_id)
            .where(DriveItemModel.user_id == self.user_id)
            .where(DriveItemModel.kind == "file")
            .where(DriveItemModel.updated_at == expected_revision)
            .values(
                storage_remote_id=remote_id,
                size=size,
                sync_status=sync_status,
                sync_error=sync_error,
                updated_at=updated_at,
            )
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="This file changed since it was opened. Reload it before saving.",
            )
        await self.session.commit()
        return await self.get(item_id)

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
