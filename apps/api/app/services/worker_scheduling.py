from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import UserModel
from app.services.deletion_service import DeletionService
from app.services.local_file_storage import LocalFileStorage


def schedule_deletion_retry(job_id: str) -> None:
    try:
        from app.worker.tasks import retry_deletion

        retry_deletion.apply_async(args=[job_id], countdown=2)
    except Exception:
        # The database record remains durable for the periodic worker sweep.
        return


async def process_deletion_jobs(user_id: str, job_ids: list[str]) -> None:
    if not job_ids:
        return
    async with SessionLocal() as session:
        user = await session.get(UserModel, user_id)
        if user is None:
            return
        service = DeletionService(session)
        await service.process_jobs(user, job_ids)


async def cleanup_local_files(remote_ids: list[str | None]) -> None:
    storage = LocalFileStorage()
    for remote_id in remote_ids:
        await storage.delete(remote_id)


def schedule_manifest_snapshot(user_id: str) -> None:
    try:
        from redis import Redis

        from app.worker.tasks import snapshot_manifest

        client = Redis.from_url(settings.redis_url)
        pending_key = f"teledrive:manifest-pending:{user_id}"
        scheduled_key = f"teledrive:manifest-scheduled:{user_id}"
        client.set(pending_key, b"1", ex=120)
        if client.set(scheduled_key, b"1", nx=True, ex=60):
            snapshot_manifest.apply_async(args=[user_id], countdown=15)
    except Exception:
        try:
            from app.worker.tasks import snapshot_manifest

            snapshot_manifest.delay(user_id)
        except Exception:
            return
