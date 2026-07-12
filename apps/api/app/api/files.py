from datetime import datetime
from io import BytesIO
from pathlib import Path
from secrets import token_hex
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, get_db_session
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.core.security import decrypt_secret
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.schemas.file import (
    CopyDriveFileToServerRequest,
    CreateFileRequest,
    CreateFolderRequest,
    DownloadZipRequest,
    DriveItem,
    UpdateDriveItemRequest,
)
from app.services.local_file_storage import LocalFileStorage
from app.services.server_files import create_server_files_storage
from app.services.sync_service import FileSyncService
from app.services.telegram_private_channel import TelegramPrivateChannelStorage


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

    def telegram_storage_for_user(user: UserModel) -> TelegramPrivateChannelStorage:
        return TelegramPrivateChannelStorage(
            telegram_session=decrypt_secret(user.telegram_session_encrypted),
            telegram_api_id=decrypt_secret(user.telegram_api_id_encrypted),
            telegram_api_hash=decrypt_secret(user.telegram_api_hash_encrypted),
        )

    async def read_file_bytes(
        item: DriveItem,
        user: UserModel,
    ) -> tuple[bytes | None, Path | None]:
        if item.kind != "file":
            return None, None
        if item.storage.remote_id and item.storage.remote_id.startswith("telegram://"):
            return await telegram_storage_for_user(user).download_document(item.storage.remote_id), None
        return None, local_storage.resolve(item.storage.remote_id)

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
        telegram_session_encrypted: str | None,
        telegram_api_id_encrypted: str | None,
        telegram_api_hash_encrypted: str | None,
    ) -> None:
        async with SessionLocal() as sync_session:
            user_repository = DriveRepository(
                sync_session,
                settings.teledrive_storage_channel,
                user_id,
            )
            user_storage = TelegramPrivateChannelStorage(
                telegram_session=decrypt_secret(telegram_session_encrypted),
                telegram_api_id=decrypt_secret(telegram_api_id_encrypted),
                telegram_api_hash=decrypt_secret(telegram_api_hash_encrypted),
            )
            service = FileSyncService(user_repository, local_storage, user_storage)
            await service.sync_file(item_id)

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
        return {"data": item}

    @router.post("/files", status_code=status.HTTP_201_CREATED)
    async def create_file(
        payload: CreateFileRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        remote_id = await storage.store_placeholder(
            name=payload.name,
            size=payload.size,
            mime_type=payload.mime_type,
        )
        item = await repository(session, user).create_file(
            payload.name,
            payload.parent_id,
            payload.size,
            payload.mime_type,
            remote_id,
        )
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
                user.telegram_session_encrypted,
                user.telegram_api_id_encrypted,
                user.telegram_api_hash_encrypted,
            )
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
            content = await telegram_storage_for_user(user).download_document(
                item.storage.remote_id
            )
            return Response(
                content=content,
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
        archive = BytesIO()
        used_names: set[str] = set()
        added_count = 0
        total_size = 0

        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
            for item_id in payload.item_ids:
                item = await repo.get(item_id)
                total_size += item.size
                if total_size > settings.teledrive_max_archive_bytes:
                    return Response(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content="The selected files exceed the archive size limit",
                    )
                content, path = await read_file_bytes(item, user)
                if content is None and path is None:
                    continue
                zip_name = unique_zip_name(item.name, used_names)
                if content is not None:
                    zip_file.writestr(zip_name, content)
                elif path is not None:
                    zip_file.write(path, arcname=zip_name)
                added_count += 1

        if added_count == 0:
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="No downloadable files found")

        archive.seek(0)
        filename = quote(zip_download_filename())
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        }
        return Response(
            content=archive.getvalue(),
            media_type="application/zip",
            headers=headers,
        )

    @router.post("/files/{item_id}/copy-to-server")
    async def copy_file_to_server(
        item_id: str,
        payload: CopyDriveFileToServerRequest,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        item = await repository(session, user).get(item_id)
        content, path = await read_file_bytes(item, user)
        if content is None and path is None:
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="File bytes not found")
        server_storage = create_server_files_storage(user)
        if content is None and path is not None and hasattr(server_storage, "write_path"):
            copied = await server_storage.write_path(payload.server_path, path, item.name)
        else:
            if content is None and path is not None:
                content = path.read_bytes()
            copied = await server_storage.write_bytes(
                payload.server_path,
                item.name,
                content,
            )
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
        return {"data": await service.sync_file(item_id)}

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
        return {"data": item}

    @router.delete("/files/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_file(
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        await repository(session, user).move_to_trash(item_id)
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
        return {"data": await repository(session, user).restore(item_id)}

    @router.delete("/trash/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    @limiter.limit("30/minute")
    async def delete_permanently(
        request: Request,
        item_id: str,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        deleted_items = await repository(session, user).delete_permanently(item_id)
        for item in deleted_items:
            if item.kind != "file":
                continue
            await local_storage.delete(item.storage.remote_id)
            await storage.delete_object(item.storage.remote_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
    @limiter.limit("10/minute")
    async def empty_trash(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        user: UserModel = Depends(get_current_user),
    ):
        deleted_items = await repository(session, user).empty_trash()
        for item in deleted_items:
            if item.kind != "file":
                continue
            await local_storage.delete(item.storage.remote_id)
            await storage.delete_object(item.storage.remote_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
