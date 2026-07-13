# TeleDrive Architecture

## Product Boundary and Operating Model

TeleDrive is a file manager. Telegram is used only as a user-owned storage transport.

The current alpha deployment model is a single trusted operator or a small trusted internal group. The operator is responsible for the host, TLS endpoint, encrypted credentials, database, backups, and any directories exposed through Server Files. This architecture is not a public, untrusted multi-tenant storage service.

TeleDrive must not become a Telegram client:

- No chat list.
- No contact list.
- No direct messaging UI.
- No timeline-style message browsing.
- No social Telegram actions.

The default storage target is a private channel called `TeleDrive Storage`. Uploaded files should be sent to that channel as Telegram documents. TeleDrive metadata stores the mapping between local file records and Telegram remote identifiers.

## API-First Layers

```txt
Vite + React + TanStack Web UI
  -> HTTP API
    -> FastAPI routers and Pydantic schemas
    -> Auth and encrypted Telegram credential/session storage
    -> Drive metadata repository
    -> Storage adapter interface
      -> Local staging storage
      -> Telegram MTProto private channel adapter
```

The web app should never call Telegram directly. Every client, including future mobile or CLI clients, should use the same HTTP API.

Browser clients authenticate with HttpOnly session cookies plus a CSRF token on mutating requests. API tokens in response bodies are compatibility fields; the web UI does not store JWTs in `localStorage`.

All file APIs require an authenticated user. Drive metadata is scoped by `user_id`, and a user's Telegram API credentials and session string are encrypted before storage.

## Storage Adapter Contract

Storage adapters are responsible for:

- Reporting provider readiness.
- Storing file bytes and returning a remote id.
- Deleting provider objects when deletion policy allows it.

The current upload phase stages bytes locally under `STORAGE_TEMP_PATH` and stores a `local://...` remote id. Telegram upload replaces that staging id with a Telegram document/message id in a later worker phase; the staging object is removed only after that mapping commits.

The sync phase exposes `POST /api/files/:id/sync`. If Telegram credentials are configured, the MTProto adapter creates or reuses the private storage channel and uploads the file as a Telegram document. If credentials are missing, the file remains local and its status becomes `waiting_for_telegram_session`.

Text edits are content revisions: TeleDrive stages the encoded text, uploads the replacement Telegram document, then switches the metadata mapping. The prior document is persisted as a deletion job and is retried by the worker using the owning user's encrypted Telegram credentials.

After completed drive mutations, TeleDrive queues a worker task to upload an encrypted `.teledrive-manifest.v1.enc` metadata snapshot to the same private channel. It retains the newest snapshot and queues obsolete documents for durable deletion. The manifest is Fernet-encrypted with a per-user key derived from `ENCRYPTION_KEY`; restoring it requires that original application key. When no valid manifest exists, the recovery import can only recreate a flat `Recovered from Telegram` folder because Telegram documents do not contain the original directory tree.

## Telegram Deletion Jobs

Permanent delete, empty trash, text edits, and manifest rotation enqueue durable `deletion_jobs` rows keyed by `(user_id, remote_id)`. The worker deletes Telegram documents in batches inside a single MTProto session. Failed jobs use capped exponential backoff. Stale `processing` jobs are reclaimed after a worker lease timeout.

Celery Beat runs `teledrive.retry_deletions` every 60 seconds in development and production worker deployments. Trash UI polls deletion jobs only while Trash or Account is open. Opening Trash may pass `?reconcile=true` so jobs whose Telegram documents are already gone are removed from the database without another delete attempt.

Recovery tools can purge orphaned channel documents directly. Those flows do not automatically clear deletion jobs, so reconcile keeps UI state aligned with the channel.

They are not responsible for:

- Folder hierarchy.
- Sharing permissions.
- User-facing file names beyond provider upload metadata.
- Business rules for retention or indexing.

## Telegram Account Storage

The Telegram adapter is based on a user's Telegram account session, not a bot token. The recommended open-source setup stores these per user through the in-app Telegram setup wizard:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION`

Per-user encrypted credentials take precedence. Server-level `.env` values are an explicit operator fallback for workers and status checks when a user has not configured credentials. The production Docker deployment requires:

- `FRONTEND_URL`
- `API_URL`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `JWT_SECRET`
- `ENCRYPTION_KEY`
- `TELEDRIVE_STORAGE_CHANNEL`

Each user can store their own encrypted Telegram API credentials and Telegram session through the API. The adapter should create or reuse the configured private channel. If the channel does not exist, the onboarding flow should ask permission to create it.

## Production Deployment Topology

`docker-compose.production.yml` uses a private Docker network for PostgreSQL, Redis, migration, API, and worker services. Only the non-root frontend nginx container binds to `127.0.0.1:8080`; a host reverse proxy terminates TLS and forwards traffic to that address. The API and worker run as an unprivileged application user.

The one-shot migration service runs `alembic upgrade head` after PostgreSQL reports healthy. API and worker startup depends on that migration completing. PostgreSQL, Redis, local upload staging, and locally managed Server Files use named volumes. Backups must include PostgreSQL and the persistent application volumes, with restoration tested separately from production.

## Metadata

The metadata repository is database-backed with SQLAlchemy async. The intended production repository contains:

- Users
- Drive items
- Folder tree
- Provider object mappings
- Upload and Telegram deletion jobs
- Encrypted manifest snapshots
- Audit events

## Roadmap

1. Automatic user-scoped sync scheduling after upload. Done in the API request path via FastAPI background tasks; Celery workers handle deletion retries and manifest work.
2. Local development stack health endpoint at `GET /api/dev/stack-status` (debug only).
3. Add download streaming from Telegram when bytes are no longer local.
4. Add provider repair jobs.
