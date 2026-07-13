from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deletion_job import DeletionJobModel
from app.models.user import UserModel
from app.services.telegram_credentials import telegram_storage_for_user

MAX_DELETE_ATTEMPTS = 12
PROCESSING_LEASE_SECONDS = 300


class DeletionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        user_id: str,
        remote_ids: list[str | None],
        *,
        commit: bool = True,
    ) -> list[str]:
        jobs: list[DeletionJobModel] = []
        for remote_id in {value for value in remote_ids if value and value.startswith("telegram://")}:
            job = await self.session.scalar(
                select(DeletionJobModel)
                .where(DeletionJobModel.user_id == user_id)
                .where(DeletionJobModel.remote_id == remote_id)
            )
            if job is None:
                job = DeletionJobModel(user_id=user_id, remote_id=remote_id)
                self.session.add(job)
            jobs.append(job)
        if commit:
            await self.session.commit()
        return [job.id for job in jobs]

    async def attempt(self, job_id: str, user: UserModel) -> bool:
        job = await self.session.get(DeletionJobModel, job_id)
        if job is None or job.user_id != user.id or job.status == "completed":
            return True
        job.status = "processing"
        job.attempts += 1
        await self.session.commit()
        storage = telegram_storage_for_user(user)
        try:
            await storage.delete_object(job.remote_id)
        except Exception as error:
            job.status = "failed"
            job.last_error = str(error)[:4096]
            delay = min(3600, 2 ** min(job.attempts, 10))
            job.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            await self.session.commit()
            return False
        await self.session.delete(job)
        await self.session.commit()
        return True

    async def due_jobs(self, limit: int = 100) -> list[DeletionJobModel]:
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(DeletionJobModel)
            .where(DeletionJobModel.status == "processing")
            .where(
                DeletionJobModel.updated_at
                <= now - timedelta(seconds=PROCESSING_LEASE_SECONDS)
            )
            .values(
                status="failed",
                next_attempt_at=now,
                last_error="Deletion worker lease expired; retrying",
            )
        )
        await self.session.commit()
        result = await self.session.scalars(
            select(DeletionJobModel)
            .where(DeletionJobModel.status.in_(("pending", "failed")))
            .where(DeletionJobModel.next_attempt_at <= now)
            .where(DeletionJobModel.attempts < MAX_DELETE_ATTEMPTS)
            .order_by(DeletionJobModel.next_attempt_at)
            .limit(limit)
        )
        return result.all()

    async def reconcile_jobs_for_user(self, user: UserModel) -> int:
        result = await self.session.scalars(
            select(DeletionJobModel)
            .where(DeletionJobModel.user_id == user.id)
            .where(DeletionJobModel.status.in_(("pending", "processing", "failed")))
        )
        jobs = result.all()
        if not jobs:
            return 0

        storage = telegram_storage_for_user(user)
        filter_existing = getattr(storage, "filter_existing_remote_ids", None)
        if filter_existing is None:
            return 0

        existing = await filter_existing([job.remote_id for job in jobs])
        removed = 0
        for job in jobs:
            if job.remote_id not in existing:
                await self.session.delete(job)
                removed += 1
        if removed:
            await self.session.commit()
        return removed

    async def list_jobs(
        self,
        user_id: str,
        limit: int = 100,
        *,
        reconcile: bool = False,
    ) -> list[DeletionJobModel]:
        await self.reclaim_stale_jobs_for_user(user_id)
        if reconcile:
            user = await self.session.get(UserModel, user_id)
            if user is not None:
                await self.reconcile_jobs_for_user(user)
        result = await self.session.scalars(
            select(DeletionJobModel)
            .where(DeletionJobModel.user_id == user_id)
            .order_by(DeletionJobModel.created_at.desc())
            .limit(limit)
        )
        return result.all()

    async def reclaim_stale_jobs_for_user(self, user_id: str) -> None:
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(DeletionJobModel)
            .where(DeletionJobModel.user_id == user_id)
            .where(DeletionJobModel.status == "processing")
            .where(
                DeletionJobModel.updated_at
                <= now - timedelta(seconds=PROCESSING_LEASE_SECONDS)
            )
            .values(
                status="failed",
                next_attempt_at=now,
                last_error="Deletion timed out; retry cleanup from Account settings",
            )
        )
        await self.session.commit()

    async def finalize_jobs_after_batch_delete(
        self,
        user: UserModel,
        job_ids: list[str],
        errors: list[str],
    ) -> None:
        error_by_remote_id: dict[str, str] = {}
        for error in errors:
            if not error.startswith("telegram://"):
                continue
            body = error.removeprefix("telegram://")
            if ": " not in body:
                continue
            remote_part, _ = body.split(": ", 1)
            error_by_remote_id[f"telegram://{remote_part}"] = error
        for job_id in job_ids:
            job = await self.session.get(DeletionJobModel, job_id)
            if job is None:
                continue
            job_error = error_by_remote_id.get(job.remote_id)
            if job_error:
                job.status = "failed"
                job.last_error = job_error[:4096]
                job.attempts += 1
                job.next_attempt_at = datetime.now(timezone.utc)
            else:
                await self.session.delete(job)
        await self.session.commit()

    async def retry_all_for_user(self, user: UserModel) -> dict[str, int]:
        await self.reclaim_stale_jobs_for_user(user.id)
        await self.reconcile_jobs_for_user(user)
        jobs = await self.list_jobs(user.id)
        if not jobs:
            return {"attempted": 0, "failed": 0, "completed": 0}
        storage = telegram_storage_for_user(user)
        remote_ids = [job.remote_id for job in jobs]
        errors = await storage.delete_remote_ids(remote_ids)
        await self.finalize_jobs_after_batch_delete(user, [job.id for job in jobs], errors)
        return {
            "attempted": len(remote_ids),
            "failed": len(errors),
            "completed": len(remote_ids) - len(errors),
        }

    async def process_jobs(self, user: UserModel, job_ids: list[str]) -> None:
        if not job_ids:
            return
        jobs = []
        remote_ids: list[str] = []
        for job_id in job_ids:
            job = await self.session.get(DeletionJobModel, job_id)
            if job is None or job.user_id != user.id:
                continue
            jobs.append(job)
            remote_ids.append(job.remote_id)
        if not remote_ids:
            return
        storage = telegram_storage_for_user(user)
        errors = await storage.delete_remote_ids(remote_ids)
        await self.finalize_jobs_after_batch_delete(user, [job.id for job in jobs], errors)
        from app.services.worker_scheduling import schedule_deletion_retry

        for job in jobs:
            if any(job.remote_id in error for error in errors):
                schedule_deletion_retry(job.id)

