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
npm run dev
```

The default URLs are:

- Web: `http://localhost:5173`
- API: `http://localhost:8000`

## Quality Checks

Run before opening a pull request:

```bash
npm run build
cd apps/api
python -m compileall app
cd ../..
```

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
