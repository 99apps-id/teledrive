## TeleDrive v0.1.0 — Alpha

First public alpha release of TeleDrive, a self-hosted web file manager backed by a user's private Telegram storage channel.

### Highlights

- **TeleDrive Storage** — upload, organize, edit, and delete files synced to your private Telegram channel.
- **Trash & lifecycle** — durable deletion queue with background worker cleanup and channel reconcile.
- **Server Files** — browse and manage VPS/server folders via local filesystem or SSH/SFTP.
- **Self-hosted deployment** — production Docker Compose stack with migrations, Redis, PostgreSQL, and health checks.
- **Update notifications** — in-app check for newer GitHub releases after login.

### Alpha notice

TeleDrive is intended for a **single trusted operator** or a small internal group. Do not expose it directly to the internet without TLS and a reverse proxy. Review `README.md` for deployment, backups, and security guidance.

### Install / upgrade

```bash
git clone https://github.com/99apps-id/teledrive.git
cd teledrive
git checkout v0.1.0
```

For production Docker deployments, back up PostgreSQL and persistent volumes first, then:

```bash
git pull --ff-only
docker compose -f docker-compose.production.yml up --build -d
```

See [CHANGELOG.md](https://github.com/99apps-id/teledrive/blob/v0.1.0/CHANGELOG.md) for the full list of changes.
