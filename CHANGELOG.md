# Changelog

All notable changes to TeleDrive are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-17

### Added

- NesaRouter-aligned dark ops-console UI (OKLCH tokens, teal identity, copper warnings).
- WebDAV mount at `/dav/` with Basic and Bearer auth (Roadmap V2).
- Local mount cache with size-based eviction and background Telegram sync for WebDAV writes.
- `GET /api/webdav/status` and Mount section in API status UI.
- Design docs: `DESIGN.md` and updated `PRODUCT.md`.

### Changed

- Frontend visual theme is dark by default to match the 99apps self-hosted console family.

## [0.1.0] - 2026-07-13

First public alpha release for a single trusted operator or small internal group.

### Added

- Web file manager with folders, upload, download, rename, delete, trash bin, multi-select, and `.zip` download.
- In-browser text editor for supported text and code files.
- Guided Telegram setup inside the app for private-channel document storage.
- Durable Telegram deletion queue with background cleanup, stale-job reclaim, and channel reconcile.
- Server Files for browsing and managing VPS/server folders (local filesystem or SSH/SFTP).
- Local user login, registration, cookie sessions, and CSRF protection on mutating API requests.
- Encrypted storage for sensitive user credentials.
- In-app update check against GitHub Releases (`GET /api/update/status`).
- Production Docker Compose deployment with frontend proxy, health checks, migrations, persistent volumes, and required secrets.
- Local dev tooling: Redis preflight, `dev:clean`, Celery Beat in `npm run dev`, stack health badge, and `npm run check`.
- Community contribution templates and automated dependency update configuration.

### Changed

- API and worker production images use Python 3.11 and run as non-root users.
- Deployment documentation describes the trusted-operator alpha model, TLS, resources, and backups.

[0.2.0]: https://github.com/99apps-id/teledrive/releases/tag/v0.2.0
[0.1.0]: https://github.com/99apps-id/teledrive/releases/tag/v0.1.0
