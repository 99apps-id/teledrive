from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.models.user import UserModel
from app.services.telegram_private_channel import TelegramPrivateChannelStorage
from app.services.telegram_credentials import telegram_storage_for_user


def create_storage_router(storage: TelegramPrivateChannelStorage) -> APIRouter:
    router = APIRouter()

    @router.get("/storage/status")
    async def storage_status(user: UserModel = Depends(get_current_user)):
        return {"data": await telegram_storage_for_user(user).status()}

    return router
