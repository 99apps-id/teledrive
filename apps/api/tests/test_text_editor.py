import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.text_editor import decode_text, encode_text


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": "editor@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_decodes_utf16_markdown_and_preserves_newlines() -> None:
    source = "# Judul\r\n\r\nTeks Indonesia"
    document = decode_text("readme.md", "text/markdown", b"\xff\xfe" + source.encode("utf-16-le"))

    assert document.content == source
    assert document.encoding == "utf-16le"
    assert document.newline == "\r\n"


def test_encodes_utf8_with_bom() -> None:
    content = encode_text("Halo\nTeleDrive", "utf-8-bom", "\n")

    assert content.startswith(b"\xef\xbb\xbf")
    assert content.decode("utf-8-sig") == "Halo\nTeleDrive"


def test_rejects_binary_content() -> None:
    with pytest.raises(HTTPException, match="Binary files"):
        decode_text("payload.txt", "text/plain", b"\x00\x01\x02")


def test_rejects_non_text_extension() -> None:
    with pytest.raises(HTTPException, match="cannot be opened"):
        decode_text("archive.zip", "application/zip", b"PK\x03\x04")


def test_server_text_api_round_trips_utf16_markdown(client: TestClient) -> None:
    account = _register(client)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    root = Path(os.environ["TELEDRIVE_SERVER_FILES_ROOT"])
    try:
        upload = client.post(
            "/api/server-files/upload",
            headers=headers,
            files={"file": ("notes.md", "# Initial".encode("utf-8"), "text/markdown")},
        )
        assert upload.status_code == 201, upload.text

        saved = client.put(
            "/api/server-files/text",
            headers=headers,
            params={"path": "notes.md"},
            json={"content": "# Updated\r\n\r\nHalo", "encoding": "utf-16le", "newline": "crlf"},
        )
        assert saved.status_code == 200, saved.text

        loaded = client.get("/api/server-files/text", headers=headers, params={"path": "notes.md"})
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["data"]["content"] == "# Updated\r\n\r\nHalo"
        assert loaded.json()["data"]["encoding"] == "utf-16le"
    finally:
        (root / "notes.md").unlink(missing_ok=True)


def test_drive_text_api_saves_a_local_revision(client: TestClient) -> None:
    account = _register(client)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    created = client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("draft.md", b"# Draft", "text/markdown")},
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    item_id = item["id"]

    saved = client.put(
        f"/api/files/{item_id}/text",
        headers=headers,
        json={
            "content": "# Revisi\n\nHalo",
            "encoding": "utf-8",
            "newline": "lf",
            "revision": item["updated_at"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["size"] == len("# Revisi\n\nHalo".encode())

    read = client.get(f"/api/files/{item_id}/text", headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["content"] == "# Revisi\n\nHalo"


def test_drive_text_api_rejects_stale_revision(client: TestClient) -> None:
    account = _register(client)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    created = client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("draft.md", b"# Draft", "text/markdown")},
    )
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    first = client.put(
        f"/api/files/{item['id']}/text",
        headers=headers,
        json={"content": "# First", "revision": item["updated_at"]},
    )
    assert first.status_code == 200, first.text
    stale = client.put(
        f"/api/files/{item['id']}/text",
        headers=headers,
        json={"content": "# Stale", "revision": item["updated_at"]},
    )
    assert stale.status_code == 409


def test_metadata_only_file_is_not_marked_synced(client: TestClient) -> None:
    account = _register(client)
    created = client.post(
        "/api/files",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        json={"name": "untitled.txt", "size": 0, "mime_type": "text/plain"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["sync_status"] == "pending_upload"


def test_permanent_delete_accepts_cleanup_queue(client: TestClient) -> None:
    account = _register(client)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    created = client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("delete-me.txt", b"remove", "text/plain")},
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["data"]["id"]
    assert client.delete(f"/api/files/{item_id}", headers=headers).status_code == 204
    removed = client.delete(f"/api/trash/{item_id}", headers=headers)
    assert removed.status_code == 202, removed.text
    assert removed.json() == {"job_ids": []}
    assert client.get("/api/deletion-jobs", headers=headers).json() == {"data": []}
