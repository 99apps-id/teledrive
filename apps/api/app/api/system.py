import asyncio
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import __version__
from app.core.config import settings

router = APIRouter()


class UpdateStatus(BaseModel):
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    release_name: str | None = None
    published_at: str | None = None
    checked: bool = False
    details: str


def _version_parts(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+){0,3})", cleaned)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _version_parts(latest)
    current_parts = _version_parts(current)
    length = max(len(latest_parts), len(current_parts))
    latest_padded = latest_parts + (0,) * (length - len(latest_parts))
    current_padded = current_parts + (0,) * (length - len(current_parts))
    return latest_padded > current_padded


class DevStackStatus(BaseModel):
    api: bool = True
    redis: bool = False
    worker: bool = False


def _ping_redis(redis_url: str) -> bool:
    try:
        from redis import Redis

        return bool(Redis.from_url(redis_url).ping())
    except Exception:
        return False


def _ping_celery_worker() -> bool:
    try:
        from app.worker.tasks import celery_app

        inspect = celery_app.control.inspect(timeout=0.5)
        return bool(inspect.ping())
    except Exception:
        return False


@router.get("/dev/stack-status", response_model=dict[str, DevStackStatus])
async def dev_stack_status():
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")

    redis_ok, worker_ok = await asyncio.gather(
        asyncio.to_thread(_ping_redis, settings.redis_url),
        asyncio.to_thread(_ping_celery_worker),
    )
    return {"data": DevStackStatus(api=True, redis=redis_ok, worker=worker_ok)}


@router.get("/update/status", response_model=dict[str, UpdateStatus])
async def update_status():
    if not settings.teledrive_update_check_enabled:
        return {
            "data": UpdateStatus(
                current_version=__version__,
                details="Update checks are disabled.",
            )
        }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                settings.teledrive_releases_api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"TeleDrive/{__version__}",
                },
            )
        if response.status_code == 404:
            return {
                "data": UpdateStatus(
                    current_version=__version__,
                    checked=True,
                    details="No public release was found.",
                )
            }
        response.raise_for_status()
        release = response.json()
        latest_version = str(release.get("tag_name") or "").strip()
        update_available = bool(
            latest_version and _is_newer_version(latest_version, __version__)
        )
        return {
            "data": UpdateStatus(
                current_version=__version__,
                latest_version=latest_version or None,
                update_available=update_available,
                release_url=release.get("html_url"),
                release_name=release.get("name") or latest_version or None,
                published_at=release.get("published_at"),
                checked=True,
                details=(
                    "A newer TeleDrive release is available."
                    if update_available
                    else "TeleDrive is up to date."
                ),
            )
        }
    except (httpx.HTTPError, ValueError) as error:
        return {
            "data": UpdateStatus(
                current_version=__version__,
                checked=False,
                details=f"Unable to check for updates: {error.__class__.__name__}.",
            )
        }
