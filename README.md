# TeleDrive

TeleDrive is a self-hosted web file manager for private storage and server file access. It has two main areas:

- **TeleDrive Storage**: files managed by TeleDrive and synced to the user's private Telegram channel.
- **Server Files**: real files on a server/VPS, accessed directly when TeleDrive is installed on the VPS or through SSH/SFTP when TeleDrive runs locally.

TeleDrive is not a Telegram client. It does not expose chats, contacts, groups, or social Telegram features. Telegram is used only as a document storage transport owned by the authenticated user.

## Features

- Local user login and registration.
- Web file manager with folders, upload, download, rename, delete, trash bin, multi-select, and `.zip` download.
- Guided Telegram setup inside the app.
- Encrypted storage for sensitive user credentials.
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

Start TeleDrive:

```powershell
npm run dev
```

Open:

- Web: `http://localhost:5173`
- API: `http://localhost:8000`

### macOS

Prerequisites:

- Git
- Node.js 20 or newer
- Python 3.11 or newer

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

Start TeleDrive:

```bash
npm run dev
```

Open `http://localhost:5173`.

### Linux

Prerequisites:

- Git
- Node.js 20 or newer
- Python 3.11 or newer

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

Start TeleDrive:

```bash
npm run dev
```

Open `http://localhost:5173`.

## First Login and Setup

1. Open the web app.
2. Create a local TeleDrive account.
3. Open **Telegram setup**.
4. Save your Telegram API ID and API Hash.
5. Follow the in-app login wizard to create a Telegram session.
6. Open **Server Files** if you want to connect a local server folder or VPS over SFTP.

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

Start the app:

```bash
npm run dev
```

Defaults:

- Web: `http://localhost:5173`
- API: `http://localhost:8000`

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

The **Server Files** area is used to access files on a server or VPS.

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

## Security Notes

Recommended deployment practices:

- Do not use the `root` user for Server Files.
- If SSH mode is used, create a dedicated limited user.
- Restrict the Server Files root folder, for example `/var/lib/teledrive-files`.
- Do not point the Server Files root to `/`, `/etc`, `/root`, or other system-critical folders.
- Use a dedicated SSH key for TeleDrive.
- Use strong `ENCRYPTION_KEY` and `JWT_SECRET` values in production.
- Do not commit `.env`, local databases, storage folders, or session files.

## Database

Local development uses SQLite by default:

```env
DATABASE_URL=sqlite+aiosqlite:///./teledrive.db
```

PostgreSQL is recommended for VPS/production deployments.

Run migrations manually from `apps/api`:

```bash
python -m alembic upgrade head
```

## Docker

The project includes a `docker-compose.yml` service layout.

```bash
docker compose up --build
```

For production, set strong `JWT_SECRET` and `ENCRYPTION_KEY` values before starting containers.

## Troubleshooting

### `Telegram session needed`

Open **Telegram setup** and complete the API ID, API Hash, phone, OTP, and optional 2FA password steps.

### `Port already in use`

Stop the process using port `5173` or `8000`, or run the API/web on another port.

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

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `PUT /api/auth/telegram-credentials`
- `POST /api/auth/telegram-login/start`
- `POST /api/auth/telegram-login/verify`
- `GET /api/files`
- `POST /api/files/upload`
- `GET /api/files/:id/download`
- `POST /api/files/download-zip`
- `GET /api/trash`
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

## Status

TeleDrive is an active self-hosted project. It is suitable for personal or small internal use, especially 1-6 users, with restricted server configuration and regular backups.
