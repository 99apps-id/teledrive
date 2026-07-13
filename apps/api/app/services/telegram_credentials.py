from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.user import UserModel
from app.services.telegram_private_channel import TelegramPrivateChannelStorage


def effective_telegram_credentials(user: UserModel) -> tuple[str, str, str]:
    """Return per-user credentials, falling back to the operator environment."""
    return (
        decrypt_secret(user.telegram_session_encrypted) or settings.telegram_session,
        decrypt_secret(user.telegram_api_id_encrypted) or settings.telegram_api_id,
        decrypt_secret(user.telegram_api_hash_encrypted) or settings.telegram_api_hash,
    )


def telegram_storage_for_user(user: UserModel) -> TelegramPrivateChannelStorage:
    session, api_id, api_hash = effective_telegram_credentials(user)
    return TelegramPrivateChannelStorage(
        telegram_session=session,
        telegram_api_id=api_id,
        telegram_api_hash=api_hash,
    )
