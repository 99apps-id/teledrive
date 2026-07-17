from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import aiofiles

from app.core.config import settings


class MountCacheService:
    """Local blob cache for WebDAV mount reads/writes.

    Separate from upload staging under ``STORAGE_TEMP_PATH``. Entries are keyed
    by drive item id. Oldest files are evicted when the cache exceeds the
    configured byte budget.
    """

    def __init__(self) -> None:
        configured = settings.teledrive_mount_cache_path.strip()
        root = Path(configured) if configured else Path(settings.storage_temp_path) / "mount-cache"
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = settings.teledrive_mount_cache_max_bytes

    def path_for(self, item_id: str) -> Path:
        safe = "".join(ch for ch in item_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / f"{safe}.bin"

    def get(self, item_id: str) -> Path | None:
        path = self.path_for(item_id)
        if path.exists() and path.is_file():
            path.touch()
            return path
        return None

    async def put_bytes(self, item_id: str, content: bytes) -> Path:
        target = self.path_for(item_id)
        temporary = self.root / f".{uuid4().hex}.tmp"
        async with aiofiles.open(temporary, "wb") as output:
            await output.write(content)
        temporary.replace(target)
        await self._evict_if_needed()
        return target

    async def put_path(self, item_id: str, source: Path) -> Path:
        target = self.path_for(item_id)
        temporary = self.root / f".{uuid4().hex}.tmp"
        async with aiofiles.open(source, "rb") as input_file, aiofiles.open(temporary, "wb") as output:
            while chunk := await input_file.read(1024 * 1024):
                await output.write(chunk)
        temporary.replace(target)
        await self._evict_if_needed()
        return target

    def delete(self, item_id: str) -> None:
        self.path_for(item_id).unlink(missing_ok=True)

    async def _evict_if_needed(self) -> None:
        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in self.root.glob("*.bin"):
            try:
                stat = path.stat()
            except OSError:
                continue
            total += stat.st_size
            entries.append((stat.st_atime or time.time(), stat.st_size, path))
        if total <= self.max_bytes:
            return
        entries.sort(key=lambda item: item[0])
        for _, size, path in entries:
            if total <= self.max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size
