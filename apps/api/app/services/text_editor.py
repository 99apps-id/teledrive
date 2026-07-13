from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from charset_normalizer import from_bytes
from fastapi import HTTPException

from app.core.config import settings

TEXT_EXTENSIONS = {
    ".bash",
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".markdown",
    ".php",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}

ENCODINGS = {
    "utf-8": "utf-8",
    "utf-8-bom": "utf-8-sig",
    "utf-16le": "utf-16-le",
    "utf-16be": "utf-16-be",
    "windows-1252": "cp1252",
}


@dataclass(frozen=True)
class TextDocument:
    content: str
    encoding: str
    newline: str


def assert_editable_text(name: str, mime_type: str | None, content: bytes) -> None:
    if len(content) > settings.teledrive_max_editor_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Text editor supports files up to {settings.teledrive_max_editor_bytes} bytes",
        )
    if Path(name).suffix.lower() not in TEXT_EXTENSIONS and not (mime_type or "").startswith("text/"):
        raise HTTPException(status_code=415, detail="This file type cannot be opened in the text editor")
    if b"\x00" in content and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise HTTPException(status_code=415, detail="Binary files cannot be opened in the text editor")


def decode_text(name: str, mime_type: str | None, content: bytes) -> TextDocument:
    assert_editable_text(name, mime_type, content)
    if content.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-bom"
    elif content.startswith(b"\xff\xfe"):
        encoding = "utf-16le"
    elif content.startswith(b"\xfe\xff"):
        encoding = "utf-16be"
    else:
        best = from_bytes(content).best()
        guessed = (best.encoding if best else "utf_8").lower().replace("_", "-")
        encoding = "windows-1252" if guessed in {"cp1252", "windows-1252"} else "utf-8"
    try:
        payload = content[2:] if encoding in {"utf-16le", "utf-16be"} else content
        text = payload.decode(ENCODINGS[encoding])
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=415,
            detail="The file encoding could not be decoded. Choose another format before editing.",
        ) from error
    newline = "\r\n" if "\r\n" in text else "\n"
    return TextDocument(content=text, encoding=encoding, newline=newline)


def encode_text(content: str, encoding: str, newline: str) -> bytes:
    codec = ENCODINGS.get(encoding)
    if codec is None:
        raise HTTPException(status_code=400, detail="Unsupported text encoding")
    if newline not in {"\n", "\r\n"}:
        raise HTTPException(status_code=400, detail="Unsupported newline format")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", newline)
    encoded = normalized.encode(codec)
    if encoding == "utf-16le":
        encoded = b"\xff\xfe" + encoded
    elif encoding == "utf-16be":
        encoded = b"\xfe\xff" + encoded
    if len(encoded) > settings.teledrive_max_editor_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Text editor supports files up to {settings.teledrive_max_editor_bytes} bytes",
        )
    return encoded
