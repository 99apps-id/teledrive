from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, get_db_session
from app.core.security import decode_access_token, verify_password
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.schemas.file import DriveItem
from app.services.local_file_storage import LocalFileStorage
from app.services.mount_cache import MountCacheService
from app.services.sync_service import FileSyncService
from app.services.telegram_credentials import telegram_storage_for_user
from app.services.telegram_private_channel import TelegramPrivateChannelStorage

DAV_NS = "DAV:"
ET.register_namespace("D", DAV_NS)

router = APIRouter(tags=["WebDAV"])
local_storage = LocalFileStorage()
mount_cache = MountCacheService()


def _repository(session: AsyncSession, user: UserModel) -> DriveRepository:
    return DriveRepository(session, settings.teledrive_storage_channel, user.id)


def _dav_href(path: str, *, collection: bool = False) -> str:
    cleaned = "/" + path.strip("/")
    if cleaned == "/":
        href = "/dav/"
    else:
        parts = [quote(part, safe="") for part in cleaned.strip("/").split("/")]
        href = "/dav/" + "/".join(parts)
        if collection:
            href += "/"
    return href


def _format_http_date(value: datetime | None) -> str:
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return format_datetime(moment.astimezone(timezone.utc), usegmt=True)


def _propfind_response(
    *,
    href: str,
    display_name: str,
    is_collection: bool,
    content_length: int = 0,
    content_type: str | None = None,
    modified: datetime | None = None,
) -> ET.Element:
    response = ET.Element(f"{{{DAV_NS}}}response")
    href_el = ET.SubElement(response, f"{{{DAV_NS}}}href")
    href_el.text = href
    propstat = ET.SubElement(response, f"{{{DAV_NS}}}propstat")
    prop = ET.SubElement(propstat, f"{{{DAV_NS}}}prop")
    ET.SubElement(prop, f"{{{DAV_NS}}}displayname").text = display_name
    ET.SubElement(prop, f"{{{DAV_NS}}}getlastmodified").text = _format_http_date(modified)
    resourcetype = ET.SubElement(prop, f"{{{DAV_NS}}}resourcetype")
    if is_collection:
        ET.SubElement(resourcetype, f"{{{DAV_NS}}}collection")
    else:
        ET.SubElement(prop, f"{{{DAV_NS}}}getcontentlength").text = str(content_length)
        ET.SubElement(prop, f"{{{DAV_NS}}}getcontenttype").text = (
            content_type or "application/octet-stream"
        )
    ET.SubElement(propstat, f"{{{DAV_NS}}}status").text = "HTTP/1.1 200 OK"
    return response


def _multistatus_xml(responses: list[ET.Element]) -> bytes:
    root = ET.Element(f"{{{DAV_NS}}}multistatus")
    for response in responses:
        root.append(response)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


async def get_webdav_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> UserModel:
    if not settings.teledrive_webdav_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WebDAV is disabled")

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        user_id = decode_access_token(token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": 'Bearer realm="TeleDrive WebDAV"'},
            )
        user = await session.get(UserModel, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    if authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization.split(" ", 1)[1].strip()).decode("utf-8")
            email, password = decoded.split(":", 1)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Basic credentials",
                headers={"WWW-Authenticate": 'Basic realm="TeleDrive WebDAV"'},
            ) from error
        result = await session.scalar(select(UserModel).where(UserModel.email == email.strip().lower()))
        if result is None or not verify_password(password, result.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": 'Basic realm="TeleDrive WebDAV"'},
            )
        return result

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": 'Basic realm="TeleDrive WebDAV", Bearer realm="TeleDrive WebDAV"'},
    )


async def _ensure_drive(session: AsyncSession, user: UserModel, repo: DriveRepository) -> None:
    if not user.drive_initialized:
        await repo.seed_if_empty()
        user.drive_initialized = True
        session.add(user)
        await session.commit()


async def _sync_item(item_id: str, user_id: str) -> None:
    async with SessionLocal() as sync_session:
        user = await sync_session.get(UserModel, user_id)
        if user is None:
            return
        repo = DriveRepository(sync_session, settings.teledrive_storage_channel, user_id)
        service = FileSyncService(repo, local_storage, telegram_storage_for_user(user))
        await service.sync_file(item_id)


def _schedule_sync(item_id: str, user_id: str) -> None:
    try:
        from app.worker.tasks import sync_file

        sync_file.delay(item_id, user_id)
    except Exception:
        # Fall back to an in-process sync when Celery/Redis is unavailable.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_sync_item(item_id, user_id))
        except RuntimeError:
            asyncio.run(_sync_item(item_id, user_id))


async def _read_item_bytes(
    item: DriveItem,
    user: UserModel,
    storage: TelegramPrivateChannelStorage,
) -> tuple[Path | None, StreamingResponse | None]:
    cached = mount_cache.get(item.id)
    if cached is not None:
        return cached, None

    remote_id = item.storage.remote_id
    if remote_id and remote_id.startswith("local://"):
        path = local_storage.resolve(remote_id)
        await mount_cache.put_path(item.id, path)
        return mount_cache.get(item.id), None

    if remote_id and remote_id.startswith("telegram://"):
        chunks: list[bytes] = []
        async for chunk in storage.download_document_stream(remote_id):
            chunks.append(chunk)
        content = b"".join(chunks)
        path = await mount_cache.put_bytes(item.id, content)
        return path, None

    raise HTTPException(status_code=404, detail="File bytes are not available")


@router.options("")
@router.options("/")
@router.options("/{path:path}")
async def webdav_options(path: str = "") -> Response:
    if not settings.teledrive_webdav_enabled:
        raise HTTPException(status_code=404, detail="WebDAV is disabled")
    return Response(
        status_code=200,
        headers={
            "Allow": "OPTIONS, GET, HEAD, PUT, DELETE, MKCOL, MOVE, PROPFIND",
            "DAV": "1",
            "MS-Author-Via": "DAV",
        },
    )


@router.api_route("", methods=["PROPFIND", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MOVE"])
@router.api_route("/", methods=["PROPFIND", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MOVE"])
@router.api_route(
    "/{path:path}",
    methods=["PROPFIND", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MOVE"],
)
async def webdav_dispatch(
    request: Request,
    path: str = "",
    session: AsyncSession = Depends(get_db_session),
    user: UserModel = Depends(get_webdav_user),
):
    repo = _repository(session, user)
    await _ensure_drive(session, user, repo)
    decoded_path = unquote(path)
    method = request.method.upper()

    if method == "PROPFIND":
        return await _handle_propfind(request, repo, decoded_path)
    if method in {"GET", "HEAD"}:
        return await _handle_get(request, repo, user, decoded_path, head_only=method == "HEAD")
    if method == "PUT":
        return await _handle_put(request, repo, user, decoded_path)
    if method == "MKCOL":
        return await _handle_mkcol(repo, decoded_path)
    if method == "DELETE":
        return await _handle_delete(repo, decoded_path)
    if method == "MOVE":
        return await _handle_move(request, repo, decoded_path)
    raise HTTPException(status_code=405, detail="Method not allowed")


async def _handle_propfind(request: Request, repo: DriveRepository, path: str) -> Response:
    depth = request.headers.get("Depth", "1")
    item = await repo.resolve_path(path)
    responses: list[ET.Element] = []

    if item is None:
        responses.append(
            _propfind_response(
                href=_dav_href("", collection=True),
                display_name="TeleDrive",
                is_collection=True,
            )
        )
        children = await repo.list(None) if depth != "0" else []
        parent_path = ""
    else:
        href_path = path.strip("/")
        responses.append(
            _propfind_response(
                href=_dav_href(href_path, collection=item.kind == "folder"),
                display_name=item.name,
                is_collection=item.kind == "folder",
                content_length=item.size,
                content_type=item.mime_type,
                modified=item.updated_at,
            )
        )
        children = await repo.list(item.id) if item.kind == "folder" and depth != "0" else []
        parent_path = href_path

    for child in children:
        child_path = f"{parent_path}/{child.name}".strip("/")
        responses.append(
            _propfind_response(
                href=_dav_href(child_path, collection=child.kind == "folder"),
                display_name=child.name,
                is_collection=child.kind == "folder",
                content_length=child.size,
                content_type=child.mime_type,
                modified=child.updated_at,
            )
        )

    return Response(
        content=_multistatus_xml(responses),
        status_code=207,
        media_type='application/xml; charset="utf-8"',
    )


async def _handle_get(
    request: Request,
    repo: DriveRepository,
    user: UserModel,
    path: str,
    *,
    head_only: bool,
) -> Response:
    item = await repo.resolve_path(path)
    if item is None or item.kind == "folder":
        raise HTTPException(status_code=405, detail="Cannot download a collection")
    storage = telegram_storage_for_user(user)
    file_path, stream = await _read_item_bytes(item, user, storage)
    headers = {
        "Content-Disposition": f'attachment; filename="{quote(item.name)}"',
        "Last-Modified": _format_http_date(item.updated_at),
    }
    if head_only:
        return Response(
            status_code=200,
            headers={
                **headers,
                "Content-Length": str(item.size),
                "Content-Type": item.mime_type or "application/octet-stream",
            },
        )
    if file_path is not None:
        return FileResponse(
            file_path,
            media_type=item.mime_type or "application/octet-stream",
            filename=item.name,
            headers=headers,
        )
    assert stream is not None
    return stream


async def _handle_put(
    request: Request,
    repo: DriveRepository,
    user: UserModel,
    path: str,
) -> Response:
    segments = [part for part in path.strip("/").split("/") if part]
    if not segments:
        raise HTTPException(status_code=405, detail="Cannot PUT to root")
    parent_segments, name = segments[:-1], segments[-1]
    parent_id: str | None = None
    if parent_segments:
        parent = await repo.resolve_path("/".join(parent_segments))
        if parent is None or parent.kind != "folder":
            raise HTTPException(status_code=409, detail="Parent collection does not exist")
        parent_id = parent.id

    body = await request.body()
    if len(body) > settings.teledrive_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {settings.teledrive_max_upload_bytes} byte limit",
        )

    existing = await repo.get_child(parent_id, name)
    remote_id, size = await local_storage.save_bytes(body)
    content_type = request.headers.get("Content-Type") or "application/octet-stream"

    created = False
    if existing is None:
        item = await repo.create_file(name, parent_id, size, content_type, remote_id)
        created = True
    else:
        if existing.kind != "file":
            raise HTTPException(status_code=405, detail="Cannot overwrite a collection")
        item = await repo.replace_file_content(
            existing.id,
            size=size,
            mime_type=content_type,
            remote_id=remote_id,
        )

    await mount_cache.put_bytes(item.id, body)
    storage_status = await telegram_storage_for_user(user).status()
    if storage_status.ready:
        _schedule_sync(item.id, user.id)
    else:
        await repo.mark_sync_waiting(item.id, storage_status.details)

    return Response(status_code=201 if created else 204)


async def _handle_mkcol(repo: DriveRepository, path: str) -> Response:
    segments = [part for part in path.strip("/").split("/") if part]
    if not segments:
        raise HTTPException(status_code=405, detail="Cannot create root")
    parent_segments, name = segments[:-1], segments[-1]
    parent_id: str | None = None
    if parent_segments:
        parent = await repo.resolve_path("/".join(parent_segments))
        if parent is None or parent.kind != "folder":
            raise HTTPException(status_code=409, detail="Parent collection does not exist")
        parent_id = parent.id
    existing = await repo.get_child(parent_id, name)
    if existing is not None:
        raise HTTPException(status_code=405, detail="Collection already exists")
    await repo.create_folder(name, parent_id)
    return Response(status_code=201)


async def _handle_delete(repo: DriveRepository, path: str) -> Response:
    item = await repo.resolve_path(path)
    if item is None:
        raise HTTPException(status_code=403, detail="Cannot delete root")
    await repo.move_to_trash(item.id)
    mount_cache.delete(item.id)
    return Response(status_code=204)


async def _handle_move(request: Request, repo: DriveRepository, path: str) -> Response:
    destination = request.headers.get("Destination")
    if not destination:
        raise HTTPException(status_code=400, detail="Destination header is required")
    # Destination may be an absolute URL; keep the path after /dav/
    marker = "/dav/"
    if marker in destination:
        dest_path = unquote(destination.split(marker, 1)[1])
    else:
        dest_path = unquote(destination.lstrip("/"))
        if dest_path.startswith("dav/"):
            dest_path = dest_path[4:]

    item = await repo.resolve_path(path)
    if item is None:
        raise HTTPException(status_code=403, detail="Cannot move root")

    segments = [part for part in dest_path.strip("/").split("/") if part]
    if not segments:
        raise HTTPException(status_code=403, detail="Invalid destination")
    parent_segments, name = segments[:-1], segments[-1]
    parent_id: str | None = None
    if parent_segments:
        parent = await repo.resolve_path("/".join(parent_segments))
        if parent is None or parent.kind != "folder":
            raise HTTPException(status_code=409, detail="Destination parent does not exist")
        parent_id = parent.id

    overwrite = request.headers.get("Overwrite", "T").upper() != "F"
    existing = await repo.get_child(parent_id, name)
    if existing is not None and existing.id != item.id:
        if not overwrite:
            raise HTTPException(status_code=412, detail="Destination exists")
        await repo.move_to_trash(existing.id)

    await repo.update(item.id, name=name, parent_id=parent_id)
    return Response(status_code=201 if existing is None else 204)
