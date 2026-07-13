import asyncio
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.config import settings
from app.services.local_file_storage import LocalFileStorage


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.parametrize("path", ["/api/files", "/api/server-files"])
def test_protected_file_endpoints_require_authentication(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_user_can_register_then_log_in(client: TestClient) -> None:
    registered = register(client, "member@example.com")

    assert registered["token_type"] == "bearer"
    assert registered["user"]["email"] == "member@example.com"
    assert registered["access_token"]

    response = client.post(
        "/api/auth/login",
        json={"email": "member@example.com", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 200
    logged_in = response.json()
    assert logged_in["user"]["id"] == registered["user"]["id"]
    assert logged_in["access_token"]


def test_registration_can_be_disabled_by_the_operator(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "teledrive_registration_enabled", False)

    response = client.post(
        "/api/auth/register",
        json={"email": "blocked@example.com", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is disabled by the operator"


def test_operator_can_toggle_registration_from_the_api(client: TestClient) -> None:
    operator = register(client, "operator@example.com")
    headers = authorization(operator["access_token"])

    status = client.get("/api/auth/registration-settings", headers=headers)
    assert status.status_code == 200
    assert status.json()["registration_enabled"] is True

    disabled = client.put(
        "/api/auth/registration-settings",
        headers=headers,
        json={"registration_enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["registration_enabled"] is False

    rejected = client.post(
        "/api/auth/register",
        json={"email": "second@example.com", "password": "correct-horse-battery-staple"},
    )
    assert rejected.status_code == 403


def test_cookie_sessions_require_csrf_on_mutating_requests(client: TestClient) -> None:
    registered = register(client, "csrf@example.com")

    rejected = client.post("/api/folders", json={"name": "No CSRF"})
    assert rejected.status_code == 403

    accepted = client.post(
        "/api/folders",
        json={"name": "With CSRF"},
        headers={"X-CSRF-Token": registered["csrf_token"]},
    )
    assert accepted.status_code == 201, accepted.text


def test_users_cannot_access_each_others_drive_items(client: TestClient) -> None:
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    alice_headers = authorization(alice["access_token"])
    bob_headers = authorization(bob["access_token"])

    created = client.post(
        "/api/folders",
        headers=alice_headers,
        json={"name": "Alice private folder"},
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["data"]["id"]

    bob_list = client.get("/api/files", headers=bob_headers)
    assert bob_list.status_code == 200
    assert {item["id"] for item in bob_list.json()["data"]}.isdisjoint({item_id})

    bob_read = client.get(f"/api/files/{item_id}", headers=bob_headers)
    assert bob_read.status_code == 404
    assert bob_read.json()["detail"] == "Drive item not found"


def test_local_server_files_reject_path_traversal(client: TestClient) -> None:
    user = register(client, "server-files@example.com")

    response = client.get(
        "/api/server-files",
        headers=authorization(user["access_token"]),
        params={"path": "../outside"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Path escapes the configured root"


def test_local_server_files_reject_symlink_escape(client: TestClient) -> None:
    user = register(client, "symlink@example.com")
    root = Path(os.environ["TELEDRIVE_SERVER_FILES_ROOT"])
    root.mkdir(exist_ok=True)
    outside = root.parent / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Creating symlinks is unavailable: {error}")

    response = client.get(
        "/api/server-files",
        headers=authorization(user["access_token"]),
        params={"path": "escape"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Path escapes the configured root"


def test_server_files_routes_require_operator(client: TestClient) -> None:
    register(client, "operator@example.com")
    member = register(client, "member@example.com")

    response = client.get(
        "/api/server-files/status",
        headers=authorization(member["access_token"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Operator access is required"


def test_local_storage_save_path_enforces_limit_and_cleans_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "teledrive_max_upload_bytes", 3)
    source = tmp_path / "too-large.bin"
    source.write_bytes(b"1234")
    storage = LocalFileStorage()
    storage.root = tmp_path / "storage"
    storage.root.mkdir()

    with pytest.raises(HTTPException, match="Content exceeds"):
        asyncio.run(storage.save_path(source))

    assert list(storage.root.iterdir()) == []


def test_production_settings_reject_weak_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET must be set to a strong secret"):
        Settings(
            app_env="production",
            jwt_secret="change-me-in-production",
            encryption_key="change-me-in-production",
        )


def test_production_settings_accept_strong_secrets() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret="j" * 32,
        encryption_key="e" * 32,
    )

    assert settings.debug is False


def test_dev_stack_status_is_available_in_debug(client: TestClient) -> None:
    response = client.get("/api/dev/stack-status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["api"] is True
    assert "redis" in payload
    assert "worker" in payload
