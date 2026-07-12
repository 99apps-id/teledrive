from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

FileKind = Literal["file", "folder"]
StorageProvider = Literal["telegram-private-channel"]


class StorageRef(BaseModel):
    provider: StorageProvider = "telegram-private-channel"
    remote_id: str | None = None
    channel_name: str


class DriveItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: FileKind
    name: str
    parent_id: str | None = None
    size: int = 0
    mime_type: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    storage: StorageRef
    sync_status: str = "local"
    sync_error: str | None = None


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None


class CreateFileRequest(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None
    size: int = Field(default=0, ge=0)
    mime_type: str | None = None


class UpdateDriveItemRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    parent_id: str | None = None


class DownloadZipRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=200)


class CopyDriveFileToServerRequest(BaseModel):
    server_path: str = ""


class StorageStatus(BaseModel):
    provider: StorageProvider = "telegram-private-channel"
    channel_name: str
    connected: bool
    ready: bool
    details: str
