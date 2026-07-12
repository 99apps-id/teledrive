from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ServerFileKind = Literal["file", "folder"]
ServerFilesMode = Literal["local", "sftp"]


class ServerFileItem(BaseModel):
    name: str
    path: str
    kind: ServerFileKind
    size: int = 0
    modified_at: datetime | None = None


class ServerFilesStatus(BaseModel):
    mode: str
    root: str
    ready: bool
    details: str


class ServerFilesConfigRequest(BaseModel):
    mode: ServerFilesMode = "sftp"
    local_root: str = "./server-files"
    sftp_host: str = ""
    sftp_port: int = Field(default=22, ge=1, le=65535)
    sftp_user: str = ""
    sftp_password: str = ""
    sftp_key_path: str = ""
    sftp_root: str = "/home/admin"


class ServerFilesConfigResponse(BaseModel):
    mode: str
    local_root: str
    sftp_host: str
    sftp_port: int
    sftp_user: str
    has_sftp_password: bool
    sftp_key_path: str
    sftp_root: str
    source: str


class CreateServerFolderRequest(BaseModel):
    path: str = ""
    name: str = Field(min_length=1)


class UpdateServerFileRequest(BaseModel):
    path: str
    name: str | None = Field(default=None, min_length=1)
    parent_path: str | None = None


class ImportServerFileRequest(BaseModel):
    path: str
    parent_id: str | None = None
