## TeleDrive v0.2.0

NesaRouter-aligned dark UI and Roadmap V2 WebDAV mount.

### Highlights

- **Dark ops-console UI** — near-black shell, teal identity, copper warnings (shared visual language with NesaRouter).
- **WebDAV mount** — `/dav/` with HTTP Basic or Bearer JWT for rclone / OS network drives.
- **Mount cache + sync** — local cache for recent blobs; WebDAV writes enqueue Telegram sync.
- **API status → WebDAV mount** — status, cache path, and rclone example in the UI.

### Notes

WebDAV is cloud-drive style access for documents, media, archives, and backups — not databases, VM images, or Docker volumes. Prefer HTTPS behind a reverse proxy in production.

### Upgrade

```bash
git fetch --tags
git checkout v0.2.0
```

Review `.env.example` for `TELEDRIVE_WEBDAV_ENABLED` and mount cache settings.
