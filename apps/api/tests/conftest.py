import asyncio
import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="teledrive-api-tests-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(TEST_ROOT / 'teledrive.db').as_posix()}",
        "STORAGE_TEMP_PATH": str(TEST_ROOT / "storage"),
        "TELEDRIVE_SERVER_FILES_MODE": "local",
        "TELEDRIVE_SERVER_FILES_ROOT": str(TEST_ROOT / "server-files"),
        "JWT_SECRET": "test-jwt-secret-that-is-at-least-32-characters",
        "ENCRYPTION_KEY": "test-encryption-key-that-is-at-least-32-characters",
    }
)

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


async def _reset_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    asyncio.run(_reset_database())
    app.state.limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def remove_test_root() -> Generator[None, None, None]:
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
