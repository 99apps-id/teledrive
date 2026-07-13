import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.deletion_job import DeletionJobModel
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.schemas.file import StorageStatus
from app.services.deletion_service import DeletionService, PROCESSING_LEASE_SECONDS
from app.services.local_file_storage import LocalFileStorage
from app.services.sync_service import FileSyncService
from app.services.telegram_credentials import effective_telegram_credentials, telegram_storage_for_user


def register(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_effective_telegram_credentials_falls_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_session", "env-session")
    monkeypatch.setattr(settings, "telegram_api_id", "12345")
    monkeypatch.setattr(settings, "telegram_api_hash", "env-hash")
    user = UserModel(
        id="user-1",
        email="user@example.com",
        password_hash="hash",
        telegram_session_encrypted=None,
        telegram_api_id_encrypted=None,
        telegram_api_hash_encrypted=None,
    )

    assert effective_telegram_credentials(user) == ("env-session", "12345", "env-hash")
    storage = telegram_storage_for_user(user)
    assert asyncio.run(storage.status()).ready is True


def test_storage_status_endpoint_uses_environment_credentials(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_session", "env-session")
    monkeypatch.setattr(settings, "telegram_api_id", "12345")
    monkeypatch.setattr(settings, "telegram_api_hash", "env-hash")
    user = register(client, "storage-status@example.com")

    response = client.get(
        "/api/storage/status",
        headers=authorization(user["access_token"]),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["ready"] is True
    assert payload["connected"] is True


@pytest.mark.asyncio
async def test_deletion_service_reclaims_stale_processing_jobs() -> None:
    async with SessionLocal() as session:
        user = UserModel(
            id="delete-user",
            email="delete@example.com",
            password_hash="hash",
        )
        session.add(user)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=PROCESSING_LEASE_SECONDS + 30)
        job = DeletionJobModel(
            user_id=user.id,
            remote_id="telegram://123/456",
            status="processing",
            attempts=2,
            updated_at=stale_time,
            next_attempt_at=stale_time,
        )
        session.add(job)
        await session.commit()

        service = DeletionService(session)
        due = await service.due_jobs()
        refreshed = await session.get(DeletionJobModel, job.id)

        assert refreshed is not None
        assert refreshed.status == "failed"
        assert "lease expired" in (refreshed.last_error or "").lower()
        assert any(candidate.id == job.id for candidate in due)


@pytest.mark.asyncio
async def test_deletion_service_reconciles_jobs_when_remote_objects_are_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_db()
    async with SessionLocal() as session:
        user = UserModel(
            id="reconcile-user",
            email="reconcile@example.com",
            password_hash="hash",
        )
        session.add(user)
        gone_job = DeletionJobModel(
            user_id=user.id,
            remote_id="telegram://123/1",
            status="pending",
        )
        active_job = DeletionJobModel(
            user_id=user.id,
            remote_id="telegram://123/2",
            status="pending",
        )
        session.add_all([gone_job, active_job])
        await session.commit()

        mock_storage = MagicMock()
        mock_storage.filter_existing_remote_ids = AsyncMock(return_value={"telegram://123/2"})
        monkeypatch.setattr(
            "app.services.deletion_service.telegram_storage_for_user",
            lambda _user: mock_storage,
        )

        service = DeletionService(session)
        removed = await service.reconcile_jobs_for_user(user)
        remaining = await service.list_jobs(user.id)

        assert removed == 1
        assert len(remaining) == 1
        assert remaining[0].remote_id == "telegram://123/2"


@pytest.mark.asyncio
async def test_sync_service_deletes_local_staging_after_success(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    local_storage = LocalFileStorage()
    local_storage.root = storage_root
    remote_id, _ = await local_storage.save_bytes(b"sync-me")
    staging_path = local_storage.resolve(remote_id)
    assert staging_path.exists()

    async with SessionLocal() as session:
        user = UserModel(id="sync-user", email="sync@example.com", password_hash="hash")
        session.add(user)
        await session.commit()
        repository = DriveRepository(session, settings.teledrive_storage_channel, user.id)
        item = await repository.create_file("note.txt", None, 7, "text/plain", remote_id)

        telegram_storage = MagicMock()
        telegram_storage.status = AsyncMock(
            return_value=StorageStatus(
                channel_name=settings.teledrive_storage_channel,
                connected=True,
                ready=True,
                details="ready",
            )
        )
        telegram_storage.upload_document = AsyncMock(return_value="telegram://1/99")

        service = FileSyncService(repository, local_storage, telegram_storage)
        synced = await service.sync_file(item.id)

        assert synced.sync_status == "synced"
        assert synced.storage.remote_id == "telegram://1/99"
        assert not staging_path.exists()
        telegram_storage.upload_document.assert_awaited_once()


def test_server_import_rejects_oversized_files(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "teledrive_max_upload_bytes", 4)
    operator = register(client, "import-limit@example.com")
    root = Path(os.environ["TELEDRIVE_SERVER_FILES_ROOT"])
    root.mkdir(exist_ok=True)
    (root / "large.bin").write_bytes(b"12345")

    response = client.post(
        "/api/server-files/import-to-drive",
        headers=authorization(operator["access_token"]),
        json={"path": "large.bin", "parent_id": None},
    )

    assert response.status_code == 413


def test_sync_upload_marks_waiting_when_only_environment_credentials_exist(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_session", "")
    monkeypatch.setattr(settings, "telegram_api_id", "")
    monkeypatch.setattr(settings, "telegram_api_hash", "")
    user = register(client, "upload-wait@example.com")
    headers = authorization(user["access_token"])

    response = client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 201, response.text
    item = response.json()["data"]
    assert item["sync_status"] in {"waiting_for_telegram_session", "local", "synced"}


def test_cleanup_manifest_snapshots_endpoint(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = register(client, "manifest-cleanup@example.com")
    headers = authorization(user["access_token"])
    cleanup = AsyncMock(return_value=3)
    monkeypatch.setattr(
        "app.api.files.ManifestService.cleanup_stale_manifests",
        cleanup,
    )

    response = client.post("/api/recovery/manifests/cleanup", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["removed"] == 3
    cleanup.assert_awaited_once()
