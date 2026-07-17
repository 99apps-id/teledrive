# Design

## Product

TeleDrive is a self-hosted web file manager for Telegram-backed private storage and Server Files access. The UI should feel like a disciplined file operations console: predictable explorer patterns, dense metadata, and clear storage readiness.

## Visual Direction

Dark network operations console shared with NesaRouter: near-black shell, layered graphite panels, measured teal identity, copper warning accents, and compact surfaces built for scanning. The feeling should be closer to a control room / file gateway than a light desktop skin or a Telegram client.

## Color Tokens

Use OKLCH color tokens only.

```css
:root {
  --bg: oklch(0.13 0.018 245);
  --shell: oklch(0.1 0.016 245);
  --surface: oklch(0.18 0.022 245);
  --surface-strong: oklch(0.235 0.03 240);
  --surface-soft: oklch(0.155 0.018 245);
  --ink: oklch(0.935 0.01 220);
  --muted: oklch(0.68 0.025 225);
  --border: oklch(0.31 0.035 235);
  --primary: oklch(0.72 0.11 188);
  --primary-strong: oklch(0.8 0.13 188);
  --accent: oklch(0.73 0.14 54);
  --success: oklch(0.72 0.13 154);
  --warning: oklch(0.78 0.14 72);
  --danger: oklch(0.68 0.17 28);
}
```

## Typography

Use a system sans stack. Product UI uses a tight fixed rem scale: 12px metadata, 14px labels/body, 16px emphasized values, 20–28px page headings.

## Components

- App shell: left navigation, top toolbar/address bar, status strip, dense file content.
- Cards: only for individual repeated or summarized objects; radius 8px.
- Buttons: compact, icon-capable, consistent states.
- Tables and logs: readable first, decorative never.
- Status pills: text plus color, never color alone.
- Auth: calm sign-in panel on the dark shell; no marketing hero.
- Telegram setup: guided steps that feel operational, not social.

## Motion

Use short 150–220ms transitions for hover, selection, and panel state changes. Respect `prefers-reduced-motion`.

## Constraints

- Prefer familiar file-management patterns over novelty.
- Keep Telegram implementation details visible only where they help users understand storage status.
- Do not look like a Telegram client, chat app, marketing landing page, or glassy SaaS dashboard.
