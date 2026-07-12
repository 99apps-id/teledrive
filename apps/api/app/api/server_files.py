from urllib.parse import quote
import json

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.core.security import encrypt_secret
from app.core.config import settings
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.schemas.server_files import (
    CreateServerFolderRequest,
    ImportServerFileRequest,
    ServerFilesConfigRequest,
    UpdateServerFileRequest,
)
from app.services.local_file_storage import LocalFileStorage
from app.services.server_files import (
    LocalServerFiles,
    config_for_user,
    config_response,
    create_server_files_storage,
    request_to_config,
)


router = APIRouter()
local_storage = LocalFileStorage()


@router.get("/server-files/status")
async def server_files_status(user: UserModel = Depends(get_current_user)):
    storage = create_server_files_storage(user)
    return {"data": storage.status()}


@router.get("/server-files/config")
async def get_server_files_config(user: UserModel = Depends(get_current_user)):
    config, source = config_for_user(user)
    return {"data": config_response(config, source)}


@router.put("/server-files/config")
async def save_server_files_config(
    payload: ServerFilesConfigRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    config = request_to_config(payload)
    existing_config, _ = config_for_user(user)
    if not config.get("sftp_password") and existing_config.get("sftp_password"):
        config["sftp_password"] = existing_config["sftp_password"]
    user.server_files_config_encrypted = encrypt_secret(json.dumps(config))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"data": config_response(config, "account")}


@router.post("/server-files/config/test")
async def test_server_files_config(
    payload: ServerFilesConfigRequest,
    user: UserModel = Depends(get_current_user),
):
    config = request_to_config(payload)
    saved_config, _ = config_for_user(user)
    if not config.get("sftp_password") and saved_config.get("sftp_password"):
        config["sftp_password"] = saved_config["sftp_password"]
    storage = create_server_files_storage(override_config=config)
    await storage.list("")
    return {"data": storage.status()}


@router.get("/server-files")
async def list_server_files(
    path: str = Query(default=""),
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.list(path)}


@router.post("/server-files/folders", status_code=status.HTTP_201_CREATED)
async def create_server_folder(
    payload: CreateServerFolderRequest,
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.make_folder(payload.path, payload.name)}


@router.post("/server-files/upload", status_code=status.HTTP_201_CREATED)
async def upload_server_file(
    path: str = "",
    file: UploadFile = File(...),
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.upload(path, file)}


@router.get("/server-files/download")
async def download_server_file(
    path: str = Query(...),
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    if isinstance(storage, LocalServerFiles):
        local_path = await storage.download_path(path)
        return FileResponse(
            local_path,
            filename=local_path.name,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(local_path.name)}",
            },
        )

    filename, content = await storage.download_bytes(path)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/server-files/import-to-drive", status_code=status.HTTP_201_CREATED)
async def import_server_file_to_drive(
    payload: ImportServerFileRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    storage = create_server_files_storage(user)
    filename, content = await storage.read_bytes(payload.path)
    remote_id, size = await local_storage.save_bytes(content)
    repository = DriveRepository(session, settings.teledrive_storage_channel, user.id)
    item = await repository.create_file(
        filename,
        payload.parent_id,
        size,
        "application/octet-stream",
        remote_id,
    )
    return {"data": item}


@router.patch("/server-files")
async def update_server_file(
    payload: UpdateServerFileRequest,
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    return {
        "data": await storage.update(
            payload.path,
            name=payload.name,
            parent_path=payload.parent_path,
        )
    }


@router.delete("/server-files", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server_file(
    path: str = Query(...),
    user: UserModel = Depends(get_current_user),
):
    storage = create_server_files_storage(user)
    await storage.delete(path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
