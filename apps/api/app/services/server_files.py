from __future__ import annotations

import asyncio
import json
import posixpath
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.user import UserModel
from app.schemas.server_files import (
    ServerFileItem,
    ServerFilesConfigRequest,
    ServerFilesConfigResponse,
    ServerFilesStatus,
)


def _clean_name(name: str) -> str:
    clean = name.strip()
    if not clean or clean in {".", ".."} or "/" in clean or "\\" in clean:
        raise HTTPException(status_code=400, detail="Invalid file or folder name")
    return clean


def _normalize_relative_path(path: str | None) -> str:
    raw = (path or "").replace("\\", "/").strip()
    if raw in {"", "."}:
        return ""
    normalized = posixpath.normpath(raw.lstrip("/"))
    if normalized in {"", "."}:
        return ""
    if normalized == ".." or normalized.startswith("../") or "/../" in normalized:
        raise HTTPException(status_code=400, detail="Path escapes the configured root")
    return normalized


def _child_path(parent: str, name: str) -> str:
    return _normalize_relative_path(posixpath.join(parent, _clean_name(name)))


def _dedupe_name(name: str, exists) -> str:
    clean = _clean_name(name)
    stem = Path(clean).stem or "file"
    suffix = Path(clean).suffix
    candidate = clean
    counter = 2
    while exists(candidate):
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


class LocalServerFiles:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def status(self) -> ServerFilesStatus:
        return ServerFilesStatus(
            mode="local",
            root=str(self.root),
            ready=self.root.exists(),
            details="Reading files directly from this server",
        )

    async def list(self, path: str = "") -> list[ServerFileItem]:
        target = self._resolve(path)
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="Server folder not found")
        items = []
        for child in target.iterdir():
            try:
                stats = child.stat()
            except OSError:
                continue
            relative = child.relative_to(self.root).as_posix()
            items.append(
                ServerFileItem(
                    name=child.name,
                    path=relative,
                    kind="folder" if child.is_dir() else "file",
                    size=0 if child.is_dir() else stats.st_size,
                    modified_at=datetime.fromtimestamp(stats.st_mtime, timezone.utc),
                )
            )
        return sorted(items, key=lambda item: (item.kind != "folder", item.name.lower()))

    async def make_folder(self, path: str, name: str) -> ServerFileItem:
        target = self._resolve(_child_path(path, name))
        target.mkdir(parents=False, exist_ok=False)
        return self._item_for(target)

    async def upload(self, path: str, upload: UploadFile) -> ServerFileItem:
        name = _clean_name(upload.filename or "upload.bin")
        target = self._resolve(_child_path(path, name))
        size = 0
        try:
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.teledrive_max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Upload exceeds the {settings.teledrive_max_upload_bytes} byte limit",
                        )
                    output.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return self._item_for(target)

    async def write_bytes(self, path: str, name: str, content: bytes) -> ServerFileItem:
        folder = self._resolve(path)
        if not folder.is_dir():
            raise HTTPException(status_code=400, detail="Destination must be a folder")
        target_name = _dedupe_name(name, lambda candidate: (folder / candidate).exists())
        target = folder / target_name
        target.write_bytes(content)
        return self._item_for(target)

    async def write_path(self, path: str, source: Path, name: str) -> ServerFileItem:
        folder = self._resolve(path)
        if not folder.is_dir():
            raise HTTPException(status_code=400, detail="Destination must be a folder")
        target_name = _dedupe_name(name, lambda candidate: (folder / candidate).exists())
        target = folder / target_name
        with source.open("rb") as input_file, target.open("wb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        return self._item_for(target)

    async def read_bytes(self, path: str) -> tuple[str, bytes]:
        target = self._resolve(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Server file not found")
        return target.name, target.read_bytes()

    async def download_path(self, path: str) -> Path:
        target = self._resolve(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Server file not found")
        return target

    async def update(
        self,
        path: str,
        *,
        name: str | None = None,
        parent_path: str | None = None,
    ) -> ServerFileItem:
        source = self._resolve(path)
        if not source.exists():
            raise HTTPException(status_code=404, detail="Server item not found")
        destination_parent = self._resolve(parent_path) if parent_path is not None else source.parent
        if not destination_parent.is_dir():
            raise HTTPException(status_code=400, detail="Destination must be a folder")
        destination_name = _clean_name(name) if name is not None else source.name
        destination = destination_parent / destination_name
        if source == destination:
            return self._item_for(source)
        if source.is_dir() and destination.resolve().is_relative_to(source.resolve()):
            raise HTTPException(status_code=400, detail="Folder cannot be moved inside itself")
        source.rename(destination)
        return self._item_for(destination)

    async def delete(self, path: str) -> None:
        target = self._resolve(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Server item not found")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def _resolve(self, path: str | None) -> Path:
        relative = _normalize_relative_path(path)
        target = (self.root / relative).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise HTTPException(status_code=400, detail="Path escapes the configured root")
        return target

    def _item_for(self, path: Path) -> ServerFileItem:
        stats = path.stat()
        return ServerFileItem(
            name=path.name,
            path=path.relative_to(self.root).as_posix(),
            kind="folder" if path.is_dir() else "file",
            size=0 if path.is_dir() else stats.st_size,
            modified_at=datetime.fromtimestamp(stats.st_mtime, timezone.utc),
        )


@dataclass
class SftpConnectionConfig:
    host: str
    port: int
    user: str
    password: str
    key_path: str
    root: str
    allow_unknown_hosts: bool = False


class SftpServerFiles:
    def __init__(self, config: SftpConnectionConfig):
        self.config = config
        self.root = posixpath.normpath(config.root or "/")

    def status(self) -> ServerFilesStatus:
        ready = bool(self.config.host and self.config.user)
        return ServerFilesStatus(
            mode="sftp",
            root=f"{self.config.user}@{self.config.host}:{self.root}" if ready else self.root,
            ready=ready,
            details="Connected through SSH/SFTP" if ready else "SFTP host and user are not configured",
        )

    async def list(self, path: str = "") -> list[ServerFileItem]:
        return await asyncio.to_thread(self._list_sync, path)

    async def make_folder(self, path: str, name: str) -> ServerFileItem:
        return await asyncio.to_thread(self._make_folder_sync, path, name)

    async def upload(self, path: str, upload: UploadFile) -> ServerFileItem:
        name = _clean_name(upload.filename or "upload.bin")
        content = await upload.read(settings.teledrive_max_upload_bytes + 1)
        if len(content) > settings.teledrive_max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {settings.teledrive_max_upload_bytes} byte limit",
            )
        return await asyncio.to_thread(self._upload_sync, path, name, content)

    async def write_bytes(self, path: str, name: str, content: bytes) -> ServerFileItem:
        return await asyncio.to_thread(self._upload_sync, path, name, content, True)

    async def read_bytes(self, path: str) -> tuple[str, bytes]:
        return await self.download_bytes(path)

    async def download_bytes(self, path: str) -> tuple[str, bytes]:
        return await asyncio.to_thread(self._download_sync, path)

    async def update(
        self,
        path: str,
        *,
        name: str | None = None,
        parent_path: str | None = None,
    ) -> ServerFileItem:
        return await asyncio.to_thread(self._update_sync, path, name, parent_path)

    async def delete(self, path: str) -> None:
        await asyncio.to_thread(self._delete_sync, path)

    def _connect(self):
        try:
            import paramiko
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="Paramiko is not installed. Install API requirements again.",
            ) from exc

        if not self.config.host or not self.config.user:
            raise HTTPException(status_code=400, detail="SFTP host and user are not configured")

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.config.allow_unknown_hosts and settings.debug:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        kwargs = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.user,
            "timeout": 15,
        }
        if self.config.key_path:
            kwargs["key_filename"] = str(Path(self.config.key_path).expanduser())
        if self.config.password:
            kwargs["password"] = self.config.password
        client.connect(**kwargs)
        return client, client.open_sftp()

    def _remote_path(self, path: str | None) -> str:
        relative = _normalize_relative_path(path)
        remote = posixpath.normpath(posixpath.join(self.root, relative))
        if remote != self.root and not remote.startswith(self.root.rstrip("/") + "/"):
            raise HTTPException(status_code=400, detail="Path escapes the configured root")
        return remote

    def _relative_path(self, remote_path: str) -> str:
        if remote_path == self.root:
            return ""
        return remote_path.removeprefix(self.root.rstrip("/") + "/")

    def _list_sync(self, path: str) -> list[ServerFileItem]:
        client, sftp = self._connect()
        try:
            remote = self._remote_path(path)
            items = []
            for entry in sftp.listdir_attr(remote):
                entry_path = posixpath.join(remote, entry.filename)
                is_folder = stat.S_ISDIR(entry.st_mode or 0)
                items.append(
                    ServerFileItem(
                        name=entry.filename,
                        path=self._relative_path(entry_path),
                        kind="folder" if is_folder else "file",
                        size=0 if is_folder else entry.st_size or 0,
                        modified_at=datetime.fromtimestamp(entry.st_mtime or 0, timezone.utc),
                    )
                )
            return sorted(items, key=lambda item: (item.kind != "folder", item.name.lower()))
        finally:
            sftp.close()
            client.close()

    def _make_folder_sync(self, path: str, name: str) -> ServerFileItem:
        client, sftp = self._connect()
        try:
            remote = self._remote_path(_child_path(path, name))
            sftp.mkdir(remote)
            return self._item_for(sftp, remote)
        finally:
            sftp.close()
            client.close()

    def _upload_sync(
        self,
        path: str,
        name: str,
        content: bytes,
        dedupe: bool = False,
    ) -> ServerFileItem:
        client, sftp = self._connect()
        try:
            target_name = _clean_name(name)
            if dedupe:
                parent = self._remote_path(path)

                def exists(candidate: str) -> bool:
                    try:
                        sftp.stat(posixpath.join(parent, candidate))
                    except FileNotFoundError:
                        return False
                    return True

                target_name = _dedupe_name(target_name, exists)
            remote = self._remote_path(_child_path(path, target_name))
            with sftp.open(remote, "wb") as output:
                output.write(content)
            return self._item_for(sftp, remote)
        finally:
            sftp.close()
            client.close()

    def _download_sync(self, path: str) -> tuple[str, bytes]:
        client, sftp = self._connect()
        try:
            remote = self._remote_path(path)
            attrs = sftp.stat(remote)
            if stat.S_ISDIR(attrs.st_mode or 0):
                raise HTTPException(status_code=400, detail="Cannot download a folder")
            with sftp.open(remote, "rb") as source:
                return posixpath.basename(remote), source.read()
        finally:
            sftp.close()
            client.close()

    def _update_sync(
        self,
        path: str,
        name: str | None,
        parent_path: str | None,
    ) -> ServerFileItem:
        client, sftp = self._connect()
        try:
            source = self._remote_path(path)
            destination_parent = (
                self._remote_path(parent_path)
                if parent_path is not None
                else posixpath.dirname(source)
            )
            destination_name = _clean_name(name) if name is not None else posixpath.basename(source)
            destination = self._remote_path(
                posixpath.join(self._relative_path(destination_parent), destination_name)
            )
            if source == destination:
                return self._item_for(sftp, source)
            attrs = sftp.stat(source)
            if stat.S_ISDIR(attrs.st_mode or 0) and destination.startswith(source.rstrip("/") + "/"):
                raise HTTPException(status_code=400, detail="Folder cannot be moved inside itself")
            sftp.rename(source, destination)
            return self._item_for(sftp, destination)
        finally:
            sftp.close()
            client.close()

    def _delete_sync(self, path: str) -> None:
        client, sftp = self._connect()
        try:
            self._delete_tree(sftp, self._remote_path(path))
        finally:
            sftp.close()
            client.close()

    def _delete_tree(self, sftp, remote: str) -> None:
        attrs = sftp.stat(remote)
        if stat.S_ISDIR(attrs.st_mode or 0):
            for entry in sftp.listdir_attr(remote):
                self._delete_tree(sftp, posixpath.join(remote, entry.filename))
            sftp.rmdir(remote)
            return
        sftp.remove(remote)

    def _item_for(self, sftp, remote: str) -> ServerFileItem:
        attrs = sftp.stat(remote)
        is_folder = stat.S_ISDIR(attrs.st_mode or 0)
        return ServerFileItem(
            name=posixpath.basename(remote),
            path=self._relative_path(remote),
            kind="folder" if is_folder else "file",
            size=0 if is_folder else attrs.st_size or 0,
            modified_at=datetime.fromtimestamp(attrs.st_mtime or 0, timezone.utc),
        )


def default_server_files_config() -> dict[str, object]:
    return {
        "mode": settings.teledrive_server_files_mode.lower().strip() or "local",
        "local_root": settings.teledrive_server_files_root,
        "sftp_host": settings.teledrive_server_files_sftp_host,
        "sftp_port": settings.teledrive_server_files_sftp_port,
        "sftp_user": settings.teledrive_server_files_sftp_user,
        "sftp_password": settings.teledrive_server_files_sftp_password,
        "sftp_key_path": settings.teledrive_server_files_sftp_key_path,
        "sftp_root": settings.teledrive_server_files_sftp_root,
        "sftp_allow_unknown_hosts": settings.teledrive_server_files_sftp_allow_unknown_hosts,
    }


def config_for_user(user: UserModel | None) -> tuple[dict[str, object], str]:
    if user and user.server_files_config_encrypted:
        try:
            config = json.loads(decrypt_secret(user.server_files_config_encrypted))
            if isinstance(config, dict):
                merged = {**default_server_files_config(), **config}
                if str(merged.get("mode") or "local").lower().strip() == "local":
                    merged["local_root"] = settings.teledrive_server_files_root
                return merged, "account"
        except (json.JSONDecodeError, ValueError):
            pass
    return default_server_files_config(), "environment"


def request_to_config(payload: ServerFilesConfigRequest) -> dict[str, object]:
    return {
        "mode": payload.mode,
        # The local filesystem is owned by the operator. Never accept a path
        # selected by an authenticated web account.
        "local_root": settings.teledrive_server_files_root,
        "sftp_host": payload.sftp_host.strip(),
        "sftp_port": payload.sftp_port,
        "sftp_user": payload.sftp_user.strip(),
        "sftp_password": payload.sftp_password,
        "sftp_key_path": payload.sftp_key_path.strip(),
        "sftp_root": payload.sftp_root.strip() or "/home/admin",
    }


def config_response(config: dict[str, object], source: str) -> ServerFilesConfigResponse:
    return ServerFilesConfigResponse(
        mode=str(config.get("mode") or "local"),
        local_root=str(config.get("local_root") or "./server-files"),
        sftp_host=str(config.get("sftp_host") or ""),
        sftp_port=int(config.get("sftp_port") or 22),
        sftp_user=str(config.get("sftp_user") or ""),
        has_sftp_password=bool(config.get("sftp_password")),
        sftp_key_path=str(config.get("sftp_key_path") or ""),
        sftp_root=str(config.get("sftp_root") or "/home/admin"),
        source=source,
    )


def create_server_files_storage(
    user: UserModel | None = None,
    override_config: dict[str, object] | None = None,
):
    config = override_config or config_for_user(user)[0]
    mode = str(config.get("mode") or "local").lower().strip()
    if mode == "sftp":
        return SftpServerFiles(
            SftpConnectionConfig(
                host=str(config.get("sftp_host") or ""),
                port=int(config.get("sftp_port") or 22),
                user=str(config.get("sftp_user") or ""),
                password=str(config.get("sftp_password") or ""),
                key_path=str(config.get("sftp_key_path") or ""),
                root=str(config.get("sftp_root") or "/home/admin"),
                allow_unknown_hosts=bool(config.get("sftp_allow_unknown_hosts")),
            )
        )
    return LocalServerFiles(str(config.get("local_root") or "./server-files"))
