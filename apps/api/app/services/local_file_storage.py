from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile

from app.core.config import settings


class LocalFileStorage:
    """Temporary byte storage before Telegram MTProto upload is wired in."""

    def __init__(self) -> None:
        self.root = Path(settings.storage_temp_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile) -> tuple[str, int]:
        object_id = str(uuid4())
        target = self._path_for(object_id)
        size = 0

        async with aiofiles.open(target, "wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                await output.write(chunk)

        return f"local://{object_id}", size

    async def save_bytes(self, content: bytes) -> tuple[str, int]:
        object_id = str(uuid4())
        target = self._path_for(object_id)
        async with aiofiles.open(target, "wb") as output:
            await output.write(content)
        return f"local://{object_id}", len(content)

    def resolve(self, remote_id: str | None) -> Path:
        if not remote_id or not remote_id.startswith("local://"):
            raise HTTPException(status_code=404, detail="File bytes are not available locally")
        path = self._path_for(remote_id.removeprefix("local://"))
        if not path.exists():
            raise HTTPException(status_code=404, detail="Local file bytes not found")
        return path

    async def delete(self, remote_id: str | None) -> None:
        if not remote_id or not remote_id.startswith("local://"):
            return
        path = self._path_for(remote_id.removeprefix("local://"))
        if path.exists():
            path.unlink()

    def _path_for(self, object_id: str) -> Path:
        safe_id = "".join(character for character in object_id if character.isalnum() or character == "-")
        if not safe_id:
            raise HTTPException(status_code=400, detail="Invalid storage object id")
        return self.root / safe_id
