from __future__ import annotations

import base64

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str = "dav@example.com") -> dict[str, str]:
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_webdav_requires_auth(client: TestClient):
    response = client.request("PROPFIND", "/dav/", headers={"Depth": "0"})
    assert response.status_code == 401


def test_webdav_propfind_mkcol_put_get_move_delete(client: TestClient):
    headers = _register(client)

    root = client.request("PROPFIND", "/dav/", headers={**headers, "Depth": "1"})
    assert root.status_code == 207, root.text
    assert b"TeleDrive" in root.content

    folder = client.request("MKCOL", "/dav/Reports", headers=headers)
    assert folder.status_code == 201, folder.text

    upload = client.put(
        "/dav/Reports/notes.txt",
        headers={**headers, "Content-Type": "text/plain"},
        content=b"hello webdav",
    )
    assert upload.status_code == 201, upload.text

    download = client.get("/dav/Reports/notes.txt", headers=headers)
    assert download.status_code == 200
    assert download.content == b"hello webdav"

    moved = client.request(
        "MOVE",
        "/dav/Reports/notes.txt",
        headers={**headers, "Destination": "/dav/Reports/renamed.txt"},
    )
    assert moved.status_code in {201, 204}, moved.text

    deleted = client.request("DELETE", "/dav/Reports/renamed.txt", headers=headers)
    assert deleted.status_code == 204, deleted.text

    missing = client.get("/dav/Reports/renamed.txt", headers=headers)
    assert missing.status_code == 404


def test_webdav_basic_auth(client: TestClient):
    _register(client, "dav-basic@example.com")
    basic = base64.b64encode(b"dav-basic@example.com:password123").decode("ascii")
    response = client.request(
        "PROPFIND",
        "/dav/",
        headers={"Authorization": f"Basic {basic}", "Depth": "0"},
    )
    assert response.status_code == 207


def test_webdav_status_endpoint(client: TestClient):
    headers = _register(client, "dav-status@example.com")
    response = client.get("/api/webdav/status", headers=headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["enabled"] is True
    assert payload["mount_path"] == "/dav/"
    assert "rclone" in payload["rclone_example"]
