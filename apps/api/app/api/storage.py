from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.core.security import decrypt_secret
from app.models.user import UserModel
from app.services.telegram_private_channel import TelegramPrivateChannelStorage


def create_storage_router(storage: TelegramPrivateChannelStorage) -> APIRouter:
    router = APIRouter()

    @router.get("/storage/status")
    async def storage_status(user: UserModel = Depends(get_current_user)):
        user_storage = TelegramPrivateChannelStorage(
            telegram_session=decrypt_secret(user.telegram_session_encrypted),
            telegram_api_id=decrypt_secret(user.telegram_api_id_encrypted),
            telegram_api_hash=decrypt_secret(user.telegram_api_hash_encrypted),
        )
        return {"data": await user_storage.status()}

    return router
