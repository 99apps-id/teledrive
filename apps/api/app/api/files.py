from datetime import datetime
import os
from pathlib import Path
from secrets import token_hex
import tempfile
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, get_db_session
from app.core.dependencies import get_current_user, require_operator
from app.core.rate_limit import limiter
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.services.deletion_service import DeletionService
from app.schemas.file import (
    BulkPermanentDeleteRequest,
    CopyDriveFileToServerRequest,
    CreateFileRequest,
    CreateFolderRequest,
    DeletionJobResponse,
    DeletionQueueResponse,
    DownloadZipRequest,
    DriveItem,
    SaveTextFileRequest,
    TextFileResponse,
    UpdateDriveItemRequest,
)
from app.services.local_file_storage import LocalFileStorage
from app.services.manifest_service import ManifestService
from app.services.server_files import create_server_files_storage
from app.services.sync_service import FileSyncService
from app.services.telegram_private_channel import TelegramPrivateChannelStorage
from app.services.telegram_credentials import telegram_storage_for_user
from app.services.text_editor import decode_text, encode_text
from app.services.worker_scheduling import (
    cleanup_local_files,
    schedule_manifest_snapshot,
)


def create_files_router(
    storage: TelegramPrivateChannelStorage,
) -> APIRouter:
    router = APIRouter()
    local_storage = LocalFileStorage()

    def repository(session: AsyncSession, user: UserModel) -> DriveRepository:
        return DriveRepository(session, settings.teledrive_storage_channel, user.id)

    def zip_download_filename() -> str:
        today = datetime.now().strftime("%m-%d-%Y")
        suffix = token_hex(2)
        return f"TeleDrive-{today}-{suffix}.zip"

    async def snapshot_after_mutation(session: AsyncSession, user: UserModel) -> None:
        schedule_manifest_snapshot(user.id)

    async def snapshot_for_user(user_id: str) -> None:
        async with SessionLocal() as snapshot_session:
            user = await snapshot_session.get(UserModel, user_id)
            if user is not None:
                await snapshot_after_mutation(snapshot_session, user)

    async def finalize_permanent_deletion(
        background_tasks: BackgroundTasks,
        user: UserModel,
        deleted_items: list[DriveItem],
        job_ids: list[str],
    ) -> None:
        async with SessionLocal() as session:
            user_model = await session.get(UserModel, user.id)
            if user_model is None:
                return
            storage = telegram_storage_for_user(user_model)
            remote_ids = [
                item.storage.remote_id
                for item in deleted_items
                if item.kind == "file" and item.storage.remote_id
            ]
            errors = await storage.delete_remote_ids(remote_ids)
            await DeletionService(session).finalize_jobs_after_batch_delete(
                user_model,
                job_ids,
                errors,
            )
        local_remote_ids = [item.storage.remote_id for item in deleted_items if item.kind == "file"]
        background_tasks.add_task(cleanup_local_files, local_remote_ids)
        background_tasks.add_task(snapshot_for_user, user.id)

    async def read_file_path(
        item: DriveItem,
        user: UserModel,
    ) -> tuple[Path | None, Path | None]:
        """Return a readable path and an optional temporary path that must be deleted."""
        if item.kind != "file":
            return None, None
        if item.storage.remote_id and item.storage.remote_id.startswith("telegram://"):
            descriptor, temporary_name = tempfile.mkstemp(
                prefix="teledrive-read-",
                dir=local_storage.root,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                await telegram_storage_for_user(user).download_document_to_path(
                    item.storage.remote_id,
                    temporary_path,
                )
                return temporary_path, temporary_path
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        return local_storage.resolve(item.storage.remote_id), None

    async def read_file_bytes(
        item: DriveItem,
        user: UserModel,
    ) -> tuple[bytes | None, Path | None]:
        path, temporary_path = await read_file_path(item, user)
        if path is None:
            return None, None
        if temporary_path is not None:
            try:
                return path.read_bytes(), None
            finally:
                temporary_path.unlink(missing_ok=True)
        return None, path

    def unique_zip_name(name: str, used_names: set[str]) -> str:
        safe_name = name.replace("\\", "/").split("/")[-1].strip() or "download"
        candidate = safe_name
        stem = Path(safe_name).stem or "download"
        suffix = Path(safe_name).suffix
        counter = 2
        while candidate.lower() in used_names:
            candidate = f"{stem} ({counter}){suffix}"
            counter += 1
        used_names.add(candidate.lower())
        return candidate

    async def sync_uploaded_file(
        item_id: str,
        user_id: str,
    ) -> None:
        async with SessionLocal() as sync_session:
            user = await sync_session.get(UserModel, user_id)
            if user is None:
                return
            user_repository = DriveRepository(
                sync_session,
                settings.teledrive_storage_channel,
                user_id,
            )
            service = FileSyncService(
                user_repository,
                local_storage,
                telegram_storage_for_user(user),
            )
            item = await service.sync_file(item_id)
            if item.sync_status == "synced":
                await snapshot_after_mutation(sync_session, user)

    @router.get("/files")
    async def list_files(
        parent_id: str | None = None,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        repo = repository(session, user)
        if not user.drive_initialized:
            await repo.seed_if_empty()
            user.drive_initialized = True
            session.add(user)
            await session.commit()
        return {"data": await repo.list(parent_id)}

    @router.get("/files/{item_id}")
    async def get_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        return {"data": await repository(session, user).get(item_id)}

    @router.post("/folders", status_code=status.HTTP_201_CREATED)
    async def create_folder(
        payload: CreateFolderRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).create_folder(payload.name, payload.parent_id)
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.post("/files", status_code=status.HTTP_201_CREATED)
    async def create_file(
        payload: CreateFileRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).create_file(
            payload.name,
            payload.parent_id,
            payload.size,
            payload.mime_type,
            None,
        )
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.post("/files/upload", status_code=status.HTTP_201_CREATED)
    @limiter.limit("30/minute")
    async def upload_file(
        request: Request,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        parent_id: str | None = Form(default=None),
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        remote_id, size = await local_storage.save_upload(file)
        repo = repository(session, user)
        item = await repo.create_file(
            file.filename or "Untitled upload",
            parent_id,
            size,
            file.content_type,
            remote_id,
        )
        user_storage = telegram_storage_for_user(user)
        storage_status = await user_storage.status()
        if not storage_status.ready:
            item = await repo.mark_sync_waiting(item.id, storage_status.details)
        else:
            background_tasks.add_task(
                sync_uploaded_file,
                item.id,
                user.id,
            )
        if item.sync_status == "synced":
            await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.get("/files/{item_id}/download")
    async def download_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).get(item_id)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.name)}",
        }
        if item.storage.remote_id and item.storage.remote_id.startswith("telegram://"):
            return StreamingResponse(
                telegram_storage_for_user(user).download_document_stream(
                    item.storage.remote_id
                ),
                media_type=item.mime_type or "application/octet-stream",
                headers=headers,
            )
        path = local_storage.resolve(item.storage.remote_id)
        return FileResponse(
            path,
            media_type=item.mime_type or "application/octet-stream",
            filename=item.name,
            headers=headers,
        )

    @router.post("/files/download-zip")
    @limiter.limit("10/minute")
    async def download_zip(
        request: Request,
        payload: DownloadZipRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        repo = repository(session, user)
        descriptor, archive_name = tempfile.mkstemp(
            prefix="teledrive-",
            suffix=".zip",
            dir=local_storage.root,
        )
        os.close(descriptor)
        archive_path = Path(archive_name)
        used_names: set[str] = set()
        added_count = 0
        total_size = 0
        limit_exceeded = False

        try:
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zip_file:
                for item_id in payload.item_ids:
                    item = await repo.get(item_id)
                    total_size += item.size
                    if total_size > settings.teledrive_max_archive_bytes:
                        limit_exceeded = True
                        break
                    source_path, temporary_path = await read_file_path(item, user)
                    if source_path is None:
                        continue
                    try:
                        zip_name = unique_zip_name(item.name, used_names)
                        zip_file.write(source_path, arcname=zip_name)
                        added_count += 1
                    finally:
                        if temporary_path is not None:
                            temporary_path.unlink(missing_ok=True)

            if limit_exceeded:
                archive_path.unlink(missing_ok=True)
                return Response(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content="The selected files exceed the archive size limit",
                )
            if added_count == 0:
                archive_path.unlink(missing_ok=True)
                return Response(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content="No downloadable files found",
                )

            filename = quote(zip_download_filename())
            headers = {
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            }
            response = FileResponse(
                archive_path,
                media_type="application/zip",
                headers=headers,
                background=BackgroundTask(archive_path.unlink, missing_ok=True),
            )
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return response

    @router.post("/files/{item_id}/copy-to-server")
    async def copy_file_to_server(
        item_id: str,
        payload: CopyDriveFileToServerRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(require_operator),
    ):
        item = await repository(session, user).get(item_id)
        source_path, temporary_path = await read_file_path(item, user)
        if source_path is None:
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="File bytes not found")
        server_storage = create_server_files_storage(user)
        try:
            if temporary_path is not None and hasattr(server_storage, "write_path"):
                copied = await server_storage.write_path(payload.server_path, source_path, item.name)
            elif temporary_path is not None:
                copied = await server_storage.write_bytes(
                    payload.server_path,
                    item.name,
                    source_path.read_bytes(),
                )
            elif hasattr(server_storage, "write_path"):
                copied = await server_storage.write_path(payload.server_path, source_path, item.name)
            else:
                copied = await server_storage.write_bytes(
                    payload.server_path,
                    item.name,
                    source_path.read_bytes(),
                )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return {"data": copied}

    @router.post("/files/{item_id}/sync")
    async def sync_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        user_storage = telegram_storage_for_user(user)
        service = FileSyncService(
            repository(session, user),
            local_storage,
            user_storage,
        )
        item = await service.sync_file(item_id)
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.get("/files/{item_id}/text", response_model=dict[str, TextFileResponse])
    async def read_drive_text_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).get(item_id)
        content, path = await read_file_bytes(item, user)
        if content is None:
            if path is None or not path.is_file():
                raise HTTPException(status_code=404, detail="File bytes not found")
            content = path.read_bytes()
        document = decode_text(item.name, item.mime_type, content)
        return {
            "data": TextFileResponse(
                name=item.name,
                content=document.content,
                encoding=document.encoding,
                newline="crlf" if document.newline == "\r\n" else "lf",
                revision=item.updated_at,
            )
        }

    @router.put("/files/{item_id}/text", response_model=dict[str, DriveItem])
    @limiter.limit("30/minute")
    async def save_drive_text_file(
        request: Request,
        item_id: str,
        payload: SaveTextFileRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        repo = repository(session, user)
        current = await repo.get(item_id)
        if current.kind != "file":
            raise HTTPException(status_code=400, detail="Only files have editable content")
        encoded = encode_text(
            payload.content,
            payload.encoding,
            "\r\n" if payload.newline == "crlf" else "\n",
        )
        staged_remote_id, size = await local_storage.save_bytes(encoded)
        old_remote_id = current.storage.remote_id
        user_storage = telegram_storage_for_user(user)
        storage_status = await user_storage.status()
        if storage_status.ready:
            new_remote_id = await user_storage.upload_document(
                path=local_storage.resolve(staged_remote_id),
                name=current.name,
                mime_type=current.mime_type,
            )
            await local_storage.delete(staged_remote_id)
            try:
                item = await repo.replace_file_content(
                    item_id,
                    remote_id=new_remote_id,
                    size=size,
                    sync_status="synced",
                    expected_revision=payload.revision,
                )
            except HTTPException:
                cleanup = DeletionService(session)
                for job_id in await cleanup.enqueue(user.id, [new_remote_id]):
                    schedule_deletion_retry(job_id)
                raise
            deletion_service = DeletionService(session)
            for job_id in await deletion_service.enqueue(user.id, [old_remote_id]):
                schedule_deletion_retry(job_id)
        else:
            item = await repo.replace_file_content(
                item_id,
                remote_id=staged_remote_id,
                size=size,
                sync_status="waiting_for_telegram_session",
                sync_error=storage_status.details,
                expected_revision=payload.revision,
            )
            deletion_service = DeletionService(session)
            for job_id in await deletion_service.enqueue(user.id, [old_remote_id]):
                schedule_deletion_retry(job_id)
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.patch("/files/{item_id}")
    async def update_file(
        item_id: str,
        payload: UpdateDriveItemRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        update_kwargs = {}
        if "name" in payload.model_fields_set:
            update_kwargs["name"] = payload.name
        if "parent_id" in payload.model_fields_set:
            update_kwargs["parent_id"] = payload.parent_id
        item = await repository(session, user).update(
            item_id,
            **update_kwargs,
        )
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.delete("/files/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        await repository(session, user).move_to_trash(item_id)
        await snapshot_after_mutation(session, user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/trash")
    async def list_trash(
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        return {"data": await repository(session, user).list_trash()}

    @router.post("/trash/{item_id}/restore")
    async def restore_from_trash(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).restore(item_id)
        await snapshot_after_mutation(session, user)
        return {"data": item}

    @router.get("/deletion-jobs", response_model=dict[str, list[DeletionJobResponse]])
    async def list_deletion_jobs(
        reconcile: bool = False,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        service = DeletionService(session)
        jobs = await service.list_jobs(user.id, reconcile=reconcile)
        return {
            "data": [
                DeletionJobResponse(
                    id=job.id,
                    status=job.status,
                    attempts=job.attempts,
                    next_attempt_at=job.next_attempt_at,
                    last_error=job.last_error,
                    created_at=job.created_at,
                )
                for job in jobs
            ]
        }

    @router.post("/deletion-jobs/retry")
    @limiter.limit("5/minute")
    async def retry_deletion_jobs(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        result = await DeletionService(session).retry_all_for_user(user)
        return {"data": result}

    @router.delete("/trash/{item_id}", status_code=status.HTTP_202_ACCEPTED, response_model=DeletionQueueResponse)
    @limiter.limit("30/minute")
    async def delete_permanently(
        request: Request,
        item_id: str,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        deleted_items = await repository(session, user).delete_permanently(item_id, commit=False)
        deletion_service = DeletionService(session)
        job_ids = await deletion_service.enqueue(
            user.id,
            [item.storage.remote_id for item in deleted_items if item.kind == "file"],
            commit=False,
        )
        await session.commit()
        await finalize_permanent_deletion(background_tasks, user, deleted_items, job_ids)
        return {"job_ids": job_ids}

    @router.post("/trash/bulk-permanent", status_code=status.HTTP_202_ACCEPTED, response_model=DeletionQueueResponse)
    @limiter.limit("10/minute")
    async def delete_permanently_bulk(
        request: Request,
        payload: BulkPermanentDeleteRequest,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        deleted_items = await repository(session, user).delete_permanently_many(
            payload.item_ids,
            commit=False,
        )
        deletion_service = DeletionService(session)
        job_ids = await deletion_service.enqueue(
            user.id,
            [item.storage.remote_id for item in deleted_items if item.kind == "file"],
            commit=False,
        )
        await session.commit()
        await finalize_permanent_deletion(background_tasks, user, deleted_items, job_ids)
        return {"job_ids": job_ids}

    @router.delete("/trash", status_code=status.HTTP_202_ACCEPTED, response_model=DeletionQueueResponse)
    @limiter.limit("10/minute")
    async def empty_trash(
        request: Request,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        deleted_items = await repository(session, user).empty_trash(commit=False)
        deletion_service = DeletionService(session)
        job_ids = await deletion_service.enqueue(
            user.id,
            [item.storage.remote_id for item in deleted_items if item.kind == "file"],
            commit=False,
        )
        await session.commit()
        await finalize_permanent_deletion(background_tasks, user, deleted_items, job_ids)
        return {"job_ids": job_ids}

    @router.post("/recovery/manifests", status_code=status.HTTP_201_CREATED)
    @limiter.limit("10/minute")
    async def create_manifest_snapshot(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        manifest = ManifestService(
            session,
            repository(session, user),
            telegram_storage_for_user(user),
            user,
        )
        snapshot = await manifest.create_snapshot()
        return {"data": {"id": snapshot.id, "created_at": snapshot.created_at}}

    @router.post("/recovery/manifests/restore")
    @limiter.limit("5/minute")
    async def restore_manifest_snapshot(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        manifest = ManifestService(
            session,
            repository(session, user),
            telegram_storage_for_user(user),
            user,
        )
        return {"data": {"restored": await manifest.restore_latest()}}

    @router.post("/recovery/manifests/cleanup")
    @limiter.limit("5/minute")
    async def cleanup_manifest_snapshots(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        manifest = ManifestService(
            session,
            repository(session, user),
            telegram_storage_for_user(user),
            user,
        )
        return {"data": {"removed": await manifest.cleanup_stale_manifests()}}

    @router.post("/recovery/channel-cleanup")
    @limiter.limit("3/minute")
    async def purge_channel_documents(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        manifest = ManifestService(
            session,
            repository(session, user),
            telegram_storage_for_user(user),
            user,
        )
        removed, errors = await manifest.purge_channel_documents()
        return {"data": {"removed": removed, "errors": errors[:5]}}

    @router.post("/recovery/telegram-import")
    @limiter.limit("5/minute")
    async def import_telegram_documents(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        manifest = ManifestService(
            session,
            repository(session, user),
            telegram_storage_for_user(user),
            user,
        )
        return {"data": {"items_processed": await manifest.import_documents()}}

    return router
