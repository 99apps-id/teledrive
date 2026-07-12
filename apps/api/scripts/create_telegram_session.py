import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


async def main() -> None:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit(
            "TELEGRAM_API_ID dan TELEGRAM_API_HASH belum terisi di file .env."
        )

    async with TelegramClient(
        StringSession(),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
    ) as client:
        session = client.session.save()

    print()
    print("TELEGRAM_SESSION:")
    print(session)
    print()
    print("Paste nilai TELEGRAM_SESSION di panel kiri TeleDrive, lalu klik Save session.")


if __name__ == "__main__":
    asyncio.run(main())
