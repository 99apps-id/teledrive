from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_for_user, encrypt_for_user
from app.models.manifest_snapshot import ManifestSnapshotModel
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.services.deletion_service import DeletionService
from app.services.telegram_private_channel import TelegramPrivateChannelStorage

MANIFEST_FILENAME = ".teledrive-manifest.v1.enc"


class ManifestService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DriveRepository,
        storage: TelegramPrivateChannelStorage,
        user: UserModel,
    ) -> None:
        self.session = session
        self.repository = repository
        self.storage = storage
        self.user = user

    async def create_snapshot(self) -> ManifestSnapshotModel:
        status = await self.storage.status()
        if not status.ready:
            raise HTTPException(status_code=409, detail="Telegram storage must be connected before creating a recovery snapshot")
        plaintext = json.dumps(
            {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": await self.repository.manifest_items(),
            },
            separators=(",", ":"),
        )
        encrypted = encrypt_for_user(self.user.id, plaintext)
        remote_id = await self._upload_encrypted(encrypted)
        previous = await self.session.scalars(
            select(ManifestSnapshotModel)
            .where(ManifestSnapshotModel.user_id == self.user.id)
        )
        previous_snapshots = previous.all()
        snapshot = ManifestSnapshotModel(
            user_id=self.user.id,
            remote_id=remote_id,
            content_encrypted=encrypted,
        )
        self.session.add(snapshot)
        deletion = DeletionService(self.session)
        job_ids = await deletion.enqueue(
            self.user.id,
            [previous.remote_id for previous in previous_snapshots if previous.remote_id],
            commit=False,
        )
        for previous in previous_snapshots:
            await self.session.delete(previous)
        await self.session.commit()
        await deletion.process_jobs(self.user, job_ids)
        await self.cleanup_stale_manifests()
        return snapshot

    async def cleanup_stale_manifests(self) -> int:
        current = await self.session.scalar(
            select(ManifestSnapshotModel)
            .where(ManifestSnapshotModel.user_id == self.user.id)
            .order_by(ManifestSnapshotModel.created_at.desc())
            .limit(1)
        )
        keep = {current.remote_id} if current and current.remote_id else set()
        stale: list[str] = []
        for document in await self.storage.list_documents():
            if document.get("name") != MANIFEST_FILENAME:
                continue
            remote_id = document.get("remote_id")
            if isinstance(remote_id, str) and remote_id not in keep:
                stale.append(remote_id)
        errors = await self.storage.delete_remote_ids(stale)
        if errors:
            raise HTTPException(
                status_code=502,
                detail=f"Removed {len(stale) - len(errors)} manifest(s); {len(errors)} failed: {errors[0]}",
            )
        return len(stale)

    async def purge_channel_documents(self, *, keep_latest_manifest: bool = True) -> tuple[int, list[str]]:
        keep: set[str] = set()
        if keep_latest_manifest:
            current = await self.session.scalar(
                select(ManifestSnapshotModel)
                .where(ManifestSnapshotModel.user_id == self.user.id)
                .order_by(ManifestSnapshotModel.created_at.desc())
                .limit(1)
            )
            if current and current.remote_id:
                keep.add(current.remote_id)
        to_delete = [
            document.get("remote_id")
            for document in await self.storage.list_documents()
            if isinstance(document.get("remote_id"), str) and document["remote_id"] not in keep
        ]
        errors = await self.storage.delete_remote_ids(to_delete)
        return len(to_delete) - len(errors), errors

    async def restore_latest(self) -> int:
        for document in await self.storage.list_documents():
            if document.get("name") != MANIFEST_FILENAME:
                continue
            remote_id = document.get("remote_id")
            if not isinstance(remote_id, str):
                continue
            try:
                raw = await self.storage.download_document(remote_id)
                payload = json.loads(decrypt_for_user(self.user.id, raw.decode("utf-8")))
                items = payload.get("items")
                if payload.get("version") != 1 or not isinstance(items, list):
                    continue
            except (InvalidToken, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                continue
            return await self.repository.restore_manifest_items(items)
        raise HTTPException(status_code=404, detail="No valid encrypted Telegram recovery manifest was found")

    async def import_documents(self) -> int:
        folder = await self.repository.get_or_create_folder("Recovered from Telegram")
        imported = 0
        for document in await self.storage.list_documents():
            if document.get("name") == MANIFEST_FILENAME:
                continue
            remote_id = document.get("remote_id")
            name = document.get("name")
            if not isinstance(remote_id, str) or not isinstance(name, str):
                continue
            await self.repository.import_telegram_file(
                name=name,
                size=int(document.get("size") or 0),
                mime_type=document.get("mime_type") if isinstance(document.get("mime_type"), str) else None,
                remote_id=remote_id,
                parent_id=folder.id,
            )
            imported += 1
        return imported

    async def _upload_encrypted(self, content: str) -> str:
        descriptor, temporary = tempfile.mkstemp(prefix="teledrive-manifest-", suffix=".enc")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content.encode("utf-8"))
            return await self.storage.upload_document(
                path=Path(temporary),
                name=MANIFEST_FILENAME,
                mime_type="application/octet-stream",
            )
        finally:
            Path(temporary).unlink(missing_ok=True)
