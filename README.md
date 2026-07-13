# TeleDrive

TeleDrive is a self-hosted web file manager for private storage and server file access. It has two main areas:

- **TeleDrive Storage**: files managed by TeleDrive and synced to the user's private Telegram channel.
- **Server Files**: real files on a server/VPS, accessed directly when TeleDrive is installed on the VPS or through SSH/SFTP when TeleDrive runs locally.

TeleDrive is not a Telegram client. It does not expose chats, contacts, groups, or social Telegram features. Telegram is used only as a document storage transport owned by the authenticated user.

## Alpha Operating Model

TeleDrive is an alpha release for a single trusted operator or a small, trusted internal group. The operator controls the host, database, encryption keys, backups, and the folders exposed through Server Files. Do not offer this deployment as a multi-tenant public file-hosting service, and do not expose it directly to the internet without a TLS-terminating reverse proxy and host firewall.

## Features

- Local user login and registration.
- Web file manager with folders, upload, download, rename, delete, trash bin, multi-select, and `.zip` download.
- In-browser text editor for supported text and code files.
- Guided Telegram setup inside the app.
- Durable Telegram deletion queue with background cleanup, stale-job reclaim, and channel reconcile.
- Encrypted storage for sensitive user credentials.
- Cookie-based browser sessions with CSRF protection on mutating API requests.
- Server Files for browsing and managing VPS/server folders.
- Hybrid server access modes:
  - local app to VPS through SSH/SFTP
  - direct local filesystem access when installed on the VPS
- FastAPI backend.
- React/Vite frontend.

## License

TeleDrive is licensed under the GNU General Public License v3.0. See `LICENSE`.

## Project Structure

```txt
apps/api          FastAPI backend, database, auth, Telegram storage, Server Files
apps/web          React/Vite frontend
packages/shared   Shared TypeScript types
docs              Technical documentation
```

## Install from GitHub

Clone the repository:

```bash
git clone https://github.com/99apps-id/teledrive.git
cd teledrive
```

### Windows

Prerequisites:

- Git for Windows
- Node.js 20 or newer
- Python 3.11 or newer
- Docker Desktop (recommended for local Redis used by the background worker)

Install dependencies:

```powershell
npm ci
cd apps/api
python -m pip install -r requirements.txt
cd ../..
```

Create your environment file:

```powershell
Copy-Item .env.example .env
```

Generate strong local secrets and put different values in `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set at least:

```env
JWT_SECRET=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-different-long-random-secret
```

Start TeleDrive with the API, web UI, Celery worker, and Beat scheduler:

```powershell
npm run dev:full
```

`dev:full` starts Redis through Docker Compose, then runs the full local stack. Use this when you need permanent Telegram deletes, background sync retries, and recovery manifest jobs.

If Redis is already running on `localhost:6381`, `npm run dev` is enough. It starts the API, web UI, worker, and Beat together.

If a previous dev session left ports stuck:

```powershell
npm run dev:clean
npm run dev
```

Open:

- Web: `http://localhost:5173`
- API: `http://localhost:8001`

If port `8000` is already used on your machine (for example by another local tool), TeleDrive development defaults to `8001`.

### macOS

Prerequisites:

- Git
- Node.js 20 or newer
- Python 3.11 or newer
- Docker Desktop (recommended for local Redis used by the background worker)

With Homebrew:

```bash
brew install git node python
```

Install dependencies:

```bash
npm ci
cd apps/api
python3 -m pip install -r requirements.txt
cd ../..
```

Create your environment file:

```bash
cp .env.example .env
```

Generate strong local secrets and put different values in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start TeleDrive with the API, web UI, and background worker:

```bash
npm run dev:full
```

If Redis is already running, `npm run dev` is enough.

Open `http://localhost:5173`.

### Linux

Prerequisites:

- Git
- Node.js 20 or newer
- Python 3.11 or newer
- Docker (recommended for local Redis used by the background worker)

Example for Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv
```

Install Node.js 20 using your preferred package manager or NodeSource, then:

```bash
npm ci
cd apps/api
python3 -m pip install -r requirements.txt
cd ../..
cp .env.example .env
```

Generate strong local secrets and put different values in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start TeleDrive with the API, web UI, and background worker:

```bash
npm run dev:full
```

If Redis is already running, `npm run dev` is enough.

Open `http://localhost:5173`.

## First Login and Setup

1. Open the web app at `http://localhost:5173`.
2. Sign in, or create the first local TeleDrive account if none exists yet.
3. Open **Telegram setup**.
4. Save your Telegram API ID and API Hash.
5. Follow the in-app login wizard to create a Telegram session.
6. If you are the designated operator, open **Server Files** to connect a local server folder or VPS over SFTP. This surface is intentionally unavailable to non-operator accounts.

The first registered account becomes the operator. Production deployments should disable registration after that account is created.

## Local Development

Install Node.js dependencies:

```bash
npm ci
```

Install Python dependencies:

```bash
cd apps/api
python -m pip install -r requirements.txt
cd ../..
```

Copy the environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Generate distinct values for `JWT_SECRET` and `ENCRYPTION_KEY` in `.env`. Keep `DATABASE_URL` pointed at `teledrive.db` for normal local work; do not point it at test databases.

### Dev scripts

Permanent delete, empty trash, Telegram cleanup, and recovery manifest jobs require **Redis** and the **Celery worker**. In local development, the recommended way to get Redis is Docker Desktop via `npm run dev:full`.

`npm run dev` now checks Redis first. If Redis is down, it tries `docker compose up -d redis` automatically. If Docker is missing or Redis still cannot start, the command stops with install instructions instead of starting a broken worker stack.

| Script | Purpose |
| --- | --- |
| `npm run dev:full` | Start Redis (Docker), API, web UI, worker, and Beat |
| `npm run dev` | Verify Redis, auto-start it with Docker when possible, then start API/web/worker/Beat |
| `npm run dev:clean` | Free stuck dev ports on Windows (`8001`, `5173`–`5175`) |
| `npm run check` | Run TypeScript typecheck and API pytest suite |
| `npm run build` | Build web and shared packages |

Start the full local stack:

```bash
npm run dev:full
```

If Redis is already running:

```bash
npm run dev
```

This command verifies Redis first. If Redis is not running, TeleDrive tries to start it with Docker Compose. Install Docker Desktop when you need permanent delete and Telegram cleanup in local development.

Defaults:

- Web: `http://localhost:5173`
- API: `http://localhost:8001`
- Redis: `localhost:6381` (via Docker Compose)

In development builds, a small **Dev stack** badge in the web UI shows API, Redis, and worker status.

### Local development troubleshooting

- If `npm run dev` fails with `Port 5173 is in use` or `Port 8001 is in use`, run `npm run dev:clean` and start again.
- On Windows, the worker uses Celery's `solo` pool to avoid `PermissionError: Access is denied` from the default prefork pool.
- If Vite moves to another port such as `5175`, close the older dev terminal, run `npm run dev:clean`, then run `npm run dev` again so the web UI returns to `5173`.
- If `dev:full` fails because Docker is not installed or not in `PATH`, start Redis another way on `6381` and use `npm run dev`.
- If login succeeds but the app immediately returns to the sign-in screen, hard refresh the browser (`Ctrl+Shift+R`) and make sure only one API process is listening on `8001`.
- If Trash shows Telegram cleanup jobs after the channel is already empty, open Trash once to reconcile job state, or use **Retry Telegram cleanup** from Account settings.

## Telegram Setup

The easiest setup path is inside the web app:

1. Sign in to TeleDrive.
2. Open **Telegram setup**.
3. Open `https://my.telegram.org/apps`.
4. Create a Telegram app to get an **API ID** and **API Hash**.
5. Save the API ID and API Hash in TeleDrive.
6. Enter your Telegram phone number.
7. Enter the OTP from Telegram.
8. If your Telegram account uses 2FA, enter the Telegram cloud password.

Telegram API credentials and sessions are stored encrypted per user. Do not commit a real `.env` file containing secrets.

## Server Files / VPS Access

The **Server Files** area is used to access files on a server or VPS. It is restricted to the designated operator account; it is not a shared-user feature.

### Mode 1: Local TeleDrive to VPS via SSH

Use this when TeleDrive runs on a local computer but should browse a VPS folder.

In the UI:

1. Open **Server Files**.
2. Click **Connection settings**.
3. Choose **VPS via SSH**.
4. Enter the host, port, username, SSH key path, and root folder.
5. Click **Test connection**.
6. Click **Save connection**.

Example:

```txt
Host: example.com
Port: 22
Username: deploy
SSH key path: /home/your-user/.ssh/id_rsa
Root folder: /home/deploy
```

### Mode 2: TeleDrive Installed Directly on the VPS

If TeleDrive runs on the same VPS, SSH is not required.

In the UI:

1. Open **Server Files**.
2. Click **Connection settings**.
3. Choose **Local server folder**.
4. Enter the server folder, for example:

```txt
/var/lib/teledrive-files
```

This mode is safer because TeleDrive does not need to store SSH credentials.

## Text Editor, deletion, and recovery

TeleDrive can edit supported text and code files in the browser from both **TeleDrive Storage** and **Server Files**. The editor preserves line endings and detects common encodings, including UTF-8 (with or without BOM), UTF-16 LE/BE, and Windows-1252. A file must be a supported text type and smaller than `TELEDRIVE_MAX_EDITOR_BYTES` (5 MiB by default); binaries are intentionally rejected.

Saving an edited TeleDrive file creates a new Telegram document before replacing its stored reference. The previous Telegram document is placed in a durable deletion queue and processed by the worker with capped exponential backoff. Celery Beat retries due deletion jobs every 60 seconds in local development. Stale in-progress jobs are reclaimed after a worker crash.

Permanent-delete and empty-trash requests return when cleanup is queued. Trash shows whether cleanup is **queued**, **processing**, or **failed**. Opening Trash reconciles jobs against the Telegram channel so UI state matches files that were already removed manually or by recovery tools. Use **Retry Telegram cleanup** from Trash or Account settings if jobs fail.

TeleDrive also stores encrypted metadata snapshots in the private storage channel. Mutations enqueue snapshot work for the Celery worker, which retains the newest snapshot and queues obsolete manifest documents for deletion. Use the Storage/Recovery panel to preview and restore the latest snapshot after reinstalling or recovering the database. The original `ENCRYPTION_KEY` is required: losing or changing it makes old manifest snapshots unreadable. If no valid snapshot is available, the fallback import scans Telegram documents into a flat `Recovered from Telegram` folder; it cannot reconstruct the original folder hierarchy.

## Security Notes

Recommended deployment practices:

- Do not use the `root` user for Server Files.
- If SSH mode is used, create a dedicated limited user.
- Restrict the Server Files root folder, for example `/var/lib/teledrive-files`.
- Do not point the Server Files root to `/`, `/etc`, `/root`, or other system-critical folders.
- Use a dedicated SSH key for TeleDrive.
- Add the SFTP host to the OS `known_hosts` file before connecting. Unknown SFTP hosts are rejected by default.
- Use strong `ENCRYPTION_KEY` and `JWT_SECRET` values in production.
- Do not commit `.env`, local databases, storage folders, or session files.

## Database

Local development uses SQLite by default:

```env
DATABASE_URL=sqlite+aiosqlite:///./teledrive.db
```

The path is relative to `apps/api` when the API starts. Do not commit local database files.

PostgreSQL is recommended for VPS/production deployments.

Run migrations manually from `apps/api`:

```bash
python -m alembic upgrade head
```

## Docker

`docker-compose.yml` is a development-only service layout. It does not include the frontend proxy or production secret enforcement.

The standalone production deployment is `docker-compose.production.yml`. It builds the React frontend into a non-root nginx container, keeps PostgreSQL, Redis, API, and worker on an internal Docker network, and exposes the web container only on `127.0.0.1:8080`. The API and worker run as an unprivileged `teledrive` user, and migrations complete before either service starts.

1. Copy the example environment file and set the required production variables:

```bash
cp .env.example .env
```

Required values are `FRONTEND_URL`, `API_URL`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `ENCRYPTION_KEY`, `TELEDRIVE_STORAGE_CHANNEL`, and `TRUSTED_PROXY_CIDRS`. Generate distinct application secrets, for example:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

2. Start the deployment:

```bash
docker compose -f docker-compose.production.yml up --build -d
docker compose -f docker-compose.production.yml ps
```

The production compose file intentionally has no secret fallbacks; Compose stops with an error if a required variable is missing. Never reuse the example values or commit the resulting `.env`.

Redis defaults to the internal `redis:6379/0` service. Set `REDIS_PASSWORD` as the raw password (special characters are URL-encoded by the API before use). Leave `REDIS_URL` empty for this default, or set an explicit, already encoded `REDIS_URL` for an external Redis provider; an explicit URL takes precedence over the component settings.

### Create the first operator account

Production registration is disabled by default. To create the initial trusted operator:

1. Set `TELEDRIVE_REGISTRATION_ENABLED=true` in `.env`.
2. Restart the production stack and register the operator account with a unique password.
3. Open **Account settings** in TeleDrive and turn off **Allow new user registration**.

The first account is the operator account. It is the only account that can use the Account settings toggle to enable or disable registration later. The toggle is stored in the database and takes effect immediately; `TELEDRIVE_REGISTRATION_ENABLED` remains the initial default before an operator changes it.

Do not leave registration enabled on an internet-accessible deployment.

### TLS, reverse proxy, and resources

Put a reverse proxy such as Caddy, nginx, or Traefik in front of `https://drive.example.com`, terminate TLS there, and proxy only to `http://127.0.0.1:8080`. Redirect HTTP to HTTPS, enable automatic certificate renewal, and set `FRONTEND_URL=https://drive.example.com` and `API_URL=https://drive.example.com/api`. Do not publish PostgreSQL, Redis, or the API port.

Set `TRUSTED_PROXY_CIDRS` to the CIDR(s) of the proxy that connects directly to the API. In the bundled deployment that is the Docker network used by the web nginx container, so inspect that stack's `*_internal` Docker network and set its subnet, for example `TRUSTED_PROXY_CIDRS=172.20.0.0/16`. The rate limiter ignores `X-Forwarded-For` unless the immediate TCP peer is in this allowlist; never set it to a public or overly broad network. The public-facing proxy must remove client-supplied `X-Forwarded-For` values and set the verified client address itself before forwarding traffic.

Size the VPS according to upload volume and worker activity. Start with at least 2 CPU cores, 2 GB RAM, and disk capacity for PostgreSQL plus the local staging volume; increase memory and storage before sustained concurrent uploads. Configure host-level disk-space monitoring and container log rotation.

### Backups and recovery

The named volumes `postgres_data`, `redis_data`, `app_storage`, and `server_files` persist data. Back up PostgreSQL with `pg_dump` or `pg_basebackup`, retain a separate copy of `app_storage` while uploads may still be staged locally, and back up any data intentionally stored in `server_files`. Store encrypted, tested backups outside the host. Record the matching `.env` secrets securely: database backups cannot recover encrypted credentials without the original `ENCRYPTION_KEY`.

Before upgrades, take a database backup, review the release notes, then run:

```bash
git pull --ff-only
docker compose -f docker-compose.production.yml up --build -d
```

The migration container applies Alembic migrations on every deployment. Test restoring a backup into an isolated environment before relying on it.

## Troubleshooting

### `Telegram session needed`

Open **Telegram setup** and complete the API ID, API Hash, phone, OTP, and optional 2FA password steps.

### `Port already in use`

Run `npm run dev:clean`, then `npm run dev`. Default dev ports are `5173` (web) and `8001` (API).

### Server Files cannot connect

Check:

- Host and port are reachable.
- Username is correct.
- SSH key path exists on the machine running TeleDrive.
- The SFTP root folder exists and the user has permission.

### Files upload but do not sync

Open **API status** and **Telegram setup**. If Telegram is not ready, files remain local or waiting until the session is configured.

### Production startup fails with secret errors

Set strong values for:

```env
JWT_SECRET=replace-with-a-long-random-secret
ENCRYPTION_KEY=replace-with-a-different-long-random-secret
```

## Important API Endpoints

Auth and session:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

Telegram setup:

- `PUT /api/auth/telegram-credentials`
- `POST /api/auth/telegram-login/start`
- `POST /api/auth/telegram-login/verify`

Drive and trash:

- `GET /api/files`
- `POST /api/files/upload`
- `GET /api/files/:id/download`
- `POST /api/files/download-zip`
- `GET /api/trash`
- `DELETE /api/trash/:id`
- `DELETE /api/trash`
- `POST /api/trash/bulk-permanent`
- `GET /api/deletion-jobs?reconcile=true`
- `POST /api/deletion-jobs/retry`

Recovery and channel maintenance:

- `POST /api/recovery/manifest`
- `POST /api/recovery/manifest/restore`
- `POST /api/recovery/manifests/cleanup`
- `POST /api/recovery/channel-cleanup`
- `POST /api/recovery/import-telegram`

Server Files and status:

- `GET /api/update/status`
- `GET /api/dev/stack-status` (development only)
- `GET /api/server-files`
- `GET /api/server-files/status`
- `GET /api/server-files/config`
- `PUT /api/server-files/config`
- `POST /api/server-files/config/test`

## Stack

- Frontend: React, Vite, TypeScript, TanStack Query/Table, Axios, lucide-react.
- Backend: FastAPI, SQLAlchemy async, Alembic, Pydantic, Uvicorn.
- Auth: JWT, bcrypt, encrypted user secrets.
- Telegram: Telethon MTProto user session.
- Server Files: local filesystem or SSH/SFTP.
- Update checks: GitHub Releases endpoint, configurable for forks.

## Roadmap

### V1

- Web-based file manager.
- API-first backend.
- Telegram private channel storage per user account.
- Server Files for local filesystem and SFTP access.

### V2

- Mount TeleDrive as an additional drive on a VPS, starting with WebDAV.
- Add local cache and background sync for mounted-drive workflows.
- Explore optional FUSE or rclone adapters after WebDAV is stable.

TeleDrive mount support is planned as cloud-drive style file access, not block storage. It is intended for documents, media, archives, and backups, not active databases, VM images, or Docker volumes.

## Status

TeleDrive is an active alpha self-hosted project. It is intended for a single trusted operator or a small internal group with restricted server configuration, TLS, and tested backups. It is not yet suitable for untrusted public multi-user hosting.
