# Security Policy

## Supported Versions

TeleDrive is currently pre-1.0. Security fixes are applied to the `main` branch.

## Reporting a Vulnerability

Please do not open a public GitHub issue for sensitive security reports.

Report privately by contacting the maintainer through the GitHub repository owner:

- GitHub: `99apps-id`
- Repository: `https://github.com/99apps-id/teledrive`

Include:

- A short description of the issue.
- Steps to reproduce.
- Affected version or commit.
- Whether secrets, files, or server access may be exposed.

## Secret Handling

Never commit real values for:

- `.env`
- `JWT_SECRET`
- `ENCRYPTION_KEY`
- Telegram API ID, API hash, or Telegram session strings
- SSH private keys
- SFTP passwords
- Local databases
- Storage folders

The app stores Telegram and Server Files credentials encrypted per account. In production, use strong unique values for `JWT_SECRET` and `ENCRYPTION_KEY`; the API refuses to start in production with known weak defaults.

## Server Files Safety

Server Files can read and modify files from a configured local folder or SFTP root. For production:

- Use a dedicated operating-system user.
- Restrict the root folder to a non-system path.
- Do not point Server Files to `/`, `/etc`, `/root`, `C:\Windows`, or other system-critical paths.
- Prefer SSH keys over passwords.
- Use least-privilege file permissions.

## Telegram Safety

TeleDrive uses a Telegram user session only as private document storage. Treat the session like a password. If a session is exposed, revoke it from Telegram and create a new one.
