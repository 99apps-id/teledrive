#!/usr/bin/env python3
"""Ensure Redis is reachable before starting the local dev worker stack."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REDIS_URL = "redis://localhost:6381/0"
WAIT_SECONDS = 20


def load_redis_url() -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return DEFAULT_REDIS_URL

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "REDIS_URL" and value.strip():
            return value.strip()
    return DEFAULT_REDIS_URL


def redis_target(redis_url: str) -> tuple[str, int]:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    return host, port


def redis_is_reachable(redis_url: str) -> bool:
    host, port = redis_target(redis_url)
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def start_redis_with_docker() -> bool:
    if not docker_available():
        return False
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "redis"],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def print_install_help(redis_url: str) -> None:
    host, port = redis_target(redis_url)
    print(
        "\nTeleDrive permanent delete, Telegram cleanup, and background sync require "
        "Redis plus the Celery worker.\n",
        file=sys.stderr,
    )
    print(
        "Redis is not reachable and Docker could not start it automatically.\n",
        file=sys.stderr,
    )
    print("Recommended fix (local development):", file=sys.stderr)
    print("  1. Install Docker Desktop: https://docs.docker.com/get-docker/", file=sys.stderr)
    print("  2. Start Docker Desktop and wait until it is running.", file=sys.stderr)
    print("  3. Run: npm run dev:full\n", file=sys.stderr)
    print(
        f"Alternative: run any Redis server on {host}:{port} and set REDIS_URL in .env, "
        "then run npm run dev again.\n",
        file=sys.stderr,
    )


def main() -> int:
    redis_url = load_redis_url()
    host, port = redis_target(redis_url)

    if redis_is_reachable(redis_url):
        print(f"Redis is reachable at {host}:{port}.")
        return 0

    print(f"Redis is not reachable at {host}:{port}. Trying Docker Compose…")
    if not start_redis_with_docker():
        print_install_help(redis_url)
        return 1

    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        if redis_is_reachable(redis_url):
            print(f"Redis is ready at {host}:{port}.")
            return 0
        time.sleep(1)

    print_install_help(redis_url)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
