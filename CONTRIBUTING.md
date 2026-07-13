# Contributing to TeleDrive

Thanks for helping improve TeleDrive.

## Development Setup

Prerequisites:

- Node.js 20 or newer
- Python 3.11 or newer
- Git

Install dependencies:

```bash
npm ci
cd apps/api
python -m pip install -r requirements.txt
cd ../..
```

Create a local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Start development:

```bash
cp .env.example .env   # first time only
npm run dev
```

For the full local stack (Redis via Docker, API, web UI, Celery worker, and Beat scheduler):

```bash
npm run dev:full
```

If Redis is already running on `localhost:6381`, `npm run dev` is enough.

On Windows, if ports are stuck after a crash:

```powershell
npm run dev:clean
npm run dev
```

The default URLs are:

- Web: `http://localhost:5173`
- API: `http://localhost:8001`
- Redis: `localhost:6381` (when using Docker Compose)

If `dev:full` fails because Docker is not installed or not in `PATH`, start Redis another way and run `npm run dev`.

## Quality Checks

Run before opening a pull request:

```bash
npm run check
npm run build
```

`npm run check` runs the TypeScript typecheck and the API pytest suite.

Optional dependency audit:

```bash
npm audit --omit=dev
```

## Pull Request Guidelines

- Keep changes focused.
- Do not commit `.env`, databases, generated storage files, screenshots, logs, or credentials.
- Include screenshots for UI changes when helpful.
- Add tests or a clear manual verification note for behavioral changes.
- Keep user-facing documentation updated.

## Security

Do not disclose security issues in public issues. See `SECURITY.md`.
