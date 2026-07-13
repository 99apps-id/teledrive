from urllib.parse import quote
import json

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_operator
from app.core.rate_limit import limiter
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
from app.schemas.file import SaveTextFileRequest, TextFileResponse
from app.services.local_file_storage import LocalFileStorage
from app.services.server_files import (
    LocalServerFiles,
    SftpServerFiles,
    config_for_user,
    config_response,
    create_server_files_storage,
    request_to_config,
)
from app.services.text_editor import decode_text, encode_text


router = APIRouter(dependencies=[Depends(require_operator)])
local_storage = LocalFileStorage()


@router.get("/server-files/status")
async def server_files_status(user: UserModel = Depends(require_operator)):
    storage = create_server_files_storage(user)
    return {"data": storage.status()}


@router.get("/server-files/config")
async def get_server_files_config(user: UserModel = Depends(require_operator)):
    config, source = config_for_user(user)
    return {"data": config_response(config, source)}


@router.put("/server-files/config")
async def save_server_files_config(
    payload: ServerFilesConfigRequest,
    user: UserModel = Depends(require_operator),
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
@limiter.limit("5/minute")
async def test_server_files_config(
    request: Request,
    payload: ServerFilesConfigRequest,
    user: UserModel = Depends(require_operator),
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
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.list(path)}


@router.post("/server-files/folders", status_code=status.HTTP_201_CREATED)
async def create_server_folder(
    payload: CreateServerFolderRequest,
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.make_folder(payload.path, payload.name)}


@router.post("/server-files/upload", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def upload_server_file(
    request: Request,
    path: str = "",
    file: UploadFile = File(...),
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    return {"data": await storage.upload(path, file)}


@router.get("/server-files/download")
async def download_server_file(
    path: str = Query(...),
    user: UserModel = Depends(require_operator),
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

    if isinstance(storage, SftpServerFiles):
        filename, content = storage.download_stream(path)
        return StreamingResponse(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
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


@router.get("/server-files/text", response_model=dict[str, TextFileResponse])
async def read_server_text_file(
    path: str = Query(...),
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    name, content = await storage.read_bytes(path)
    document = decode_text(name, None, content)
    return {
        "data": TextFileResponse(
            name=name,
            content=document.content,
            encoding=document.encoding,
            newline="crlf" if document.newline == "\r\n" else "lf",
        )
    }


@router.put("/server-files/text", response_model=dict[str, TextFileResponse])
@limiter.limit("30/minute")
async def save_server_text_file(
    request: Request,
    path: str = Query(...),
    payload: SaveTextFileRequest = ...,
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    content = encode_text(payload.content, payload.encoding, "\r\n" if payload.newline == "crlf" else "\n")
    item = await storage.overwrite_bytes(path, content)
    return {
        "data": TextFileResponse(
            name=item.name,
            content=payload.content,
            encoding=payload.encoding,
            newline=payload.newline,
        )
    }


@router.post("/server-files/import-to-drive", status_code=status.HTTP_201_CREATED)
async def import_server_file_to_drive(
    payload: ImportServerFileRequest,
    user: UserModel = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
):
    storage = create_server_files_storage(user)
    if isinstance(storage, LocalServerFiles):
        source_path = await storage.download_path(payload.path)
        filename = source_path.name
        remote_id, size = await local_storage.save_path(source_path)
    else:
        filename, remote_id, size = await storage.download_to_local_storage(
            payload.path,
            local_storage,
        )
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
    user: UserModel = Depends(require_operator),
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
@limiter.limit("30/minute")
async def delete_server_file(
    request: Request,
    path: str = Query(...),
    user: UserModel = Depends(require_operator),
):
    storage = create_server_files_storage(user)
    await storage.delete(path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
