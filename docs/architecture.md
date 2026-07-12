# TeleDrive Architecture

## Product Boundary

TeleDrive is a file manager. Telegram is used only as a user-owned storage transport.

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

All file APIs require an authenticated user. Drive metadata is scoped by `user_id`, and a user's Telegram API credentials and session string are encrypted before storage.

## Storage Adapter Contract

Storage adapters are responsible for:

- Reporting provider readiness.
- Storing file bytes and returning a remote id.
- Deleting provider objects when deletion policy allows it.

The current upload phase stages bytes locally under `STORAGE_TEMP_PATH` and stores a `local://...` remote id. Telegram upload will replace that staging id with a Telegram document/message id in a later worker phase.

The sync phase exposes `POST /api/files/:id/sync`. If Telegram credentials are configured, the MTProto adapter creates or reuses the private storage channel and uploads the file as a Telegram document. If credentials are missing, the file remains local and its status becomes `waiting_for_telegram_session`.

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

Server-level `.env` values for those keys are optional fallbacks for local development or admin-managed installs. Required server configuration:

- `ENCRYPTION_KEY`
- `TELEDRIVE_STORAGE_CHANNEL`

Each user can store their own encrypted Telegram API credentials and Telegram session through the API. The adapter should create or reuse the configured private channel. If the channel does not exist, the onboarding flow should ask permission to create it.

## Metadata

The metadata repository is database-backed with SQLAlchemy async. The intended production repository contains:

- Users
- Drive items
- Folder tree
- Provider object mappings
- Upload jobs
- Audit events

## Roadmap

1. Automatic user-scoped sync scheduling after upload. Done in the API request path via FastAPI background tasks; Celery worker scaffolding keeps the same user-aware sync contract.
2. Add download streaming from Telegram when bytes are no longer local.
3. Add provider repair jobs.
