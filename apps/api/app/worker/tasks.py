from celery import Celery
import asyncio

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.deletion_job import DeletionJobModel
from app.models.user import UserModel
from app.repositories.drive_repository import DriveRepository
from app.services.deletion_service import DeletionService
from app.services.local_file_storage import LocalFileStorage
from app.services.manifest_service import ManifestService
from app.services.sync_service import FileSyncService
from app.services.telegram_credentials import telegram_storage_for_user
from app.services.worker_scheduling import schedule_manifest_snapshot

celery_app = Celery(
    "teledrive",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.beat_schedule = {
    "retry-telegram-deletions": {
        "task": "teledrive.retry_deletions",
        "schedule": 60.0,
    }
}


@celery_app.task(name="teledrive.health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="teledrive.sync_file")
def sync_file(
    item_id: str,
    user_id: str,
) -> dict[str, str | None]:
    return asyncio.run(_sync_file(item_id, user_id))


async def _sync_file(
    item_id: str,
    user_id: str,
) -> dict[str, str | None]:
    async with SessionLocal() as session:
        user = await session.get(UserModel, user_id)
        if user is None:
            return {"id": item_id, "sync_status": "failed", "remote_id": None}
        repository = DriveRepository(session, settings.teledrive_storage_channel, user_id)
        service = FileSyncService(
            repository,
            LocalFileStorage(),
            telegram_storage_for_user(user),
        )
        item = await service.sync_file(item_id)
        if item.sync_status == "synced":
            schedule_manifest_snapshot(user_id)
        return {
            "id": item.id,
            "sync_status": item.sync_status,
            "remote_id": item.storage.remote_id,
        }


@celery_app.task(name="teledrive.snapshot_manifest")
def snapshot_manifest(user_id: str) -> bool:
    return asyncio.run(_snapshot_manifest(user_id))


async def _snapshot_manifest(user_id: str) -> bool:
    scheduled_key = f"teledrive:manifest-scheduled:{user_id}"
    pending_key = f"teledrive:manifest-pending:{user_id}"
    succeeded = False
    try:
        async with SessionLocal() as session:
            user = await session.get(UserModel, user_id)
            if user is None:
                return False
            try:
                await ManifestService(
                    session,
                    DriveRepository(session, settings.teledrive_storage_channel, user.id),
                    telegram_storage_for_user(user),
                    user,
                ).create_snapshot()
                succeeded = True
            except Exception:
                succeeded = False
    finally:
        try:
            from redis import Redis

            client = Redis.from_url(settings.redis_url)
            client.delete(scheduled_key)
            if client.exists(pending_key):
                client.delete(pending_key)
                snapshot_manifest.apply_async(args=[user_id], countdown=15)
        except Exception:
            pass
    return succeeded


@celery_app.task(name="teledrive.retry_deletions")
def retry_deletions() -> dict[str, int]:
    return asyncio.run(_retry_deletions())


async def _retry_deletions() -> dict[str, int]:
    attempted = 0
    completed = 0
    async with SessionLocal() as session:
        service = DeletionService(session)
        jobs = await service.due_jobs()
        for job in jobs:
            user = await session.get(UserModel, job.user_id)
            if user is None:
                job.status = "failed"
                job.last_error = "User no longer exists"
                await session.commit()
                continue
            attempted += 1
            if await service.attempt(job.id, user):
                completed += 1
    return {"attempted": attempted, "completed": completed}


@celery_app.task(name="teledrive.retry_deletion")
def retry_deletion(job_id: str) -> bool:
    return asyncio.run(_retry_deletion(job_id))


async def _retry_deletion(job_id: str) -> bool:
    async with SessionLocal() as session:
        job = await session.get(DeletionJobModel, job_id)
        if job is None or job.status == "completed":
            return True
        if job.attempts >= 12:
            return False
        user = await session.get(UserModel, job.user_id)
        if user is None:
            job.status = "failed"
            job.last_error = "User no longer exists"
            await session.commit()
            return False
        service = DeletionService(session)
        completed = await service.attempt(job_id, user)
        if not completed:
            refreshed = await session.get(DeletionJobModel, job_id)
            if refreshed is not None and refreshed.attempts < 12:
                delay = max(
                    1,
                    int((refreshed.next_attempt_at - refreshed.updated_at).total_seconds()),
                )
                retry_deletion.apply_async(args=[job_id], countdown=delay)
        return completed
