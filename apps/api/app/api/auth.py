from uuid import uuid4

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.models.user import UserModel
from app.models.app_setting import AppSettingModel
from app.core.config import settings
from app.schemas.auth import (
    AccountUpdateRequest,
    AuthRequest,
    AuthResponse,
    RegistrationSettingsRequest,
    RegistrationSettingsResponse,
    TelegramCredentialsRequest,
    TelegramLoginResponse,
    TelegramLoginStartRequest,
    TelegramLoginVerifyRequest,
    TelegramSessionRequest,
    UserResponse,
)

router = APIRouter()


def _user_response(user: UserModel) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        is_operator=user.is_operator,
        has_telegram_api_credentials=bool(
            user.telegram_api_id_encrypted
            and user.telegram_api_hash_encrypted
            or settings.telegram_api_id
            and settings.telegram_api_hash
        ),
        has_telegram_session=bool(user.telegram_session_encrypted),
    )


def _telegram_credentials(user: UserModel) -> tuple[int, str]:
    api_id = decrypt_secret(user.telegram_api_id_encrypted) or settings.telegram_api_id
    api_hash = decrypt_secret(user.telegram_api_hash_encrypted) or settings.telegram_api_hash
    if not api_id or not api_hash:
        raise HTTPException(
            status_code=400,
            detail="Save Telegram API ID and API Hash before starting Telegram login.",
        )
    try:
        return int(api_id), api_hash
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Telegram API ID must be a number.") from error


async def _registration_enabled(session: AsyncSession) -> bool:
    setting = await session.get(AppSettingModel, "registration_enabled")
    return setting.bool_value if setting is not None else settings.registration_enabled


def _require_operator(user: UserModel) -> None:
    if not user.is_operator:
        raise HTTPException(status_code=403, detail="Operator access is required")


def _clear_pending_telegram_login(user: UserModel) -> None:
    user.telegram_login_phone_encrypted = None
    user.telegram_login_code_hash_encrypted = None
    user.telegram_login_session_encrypted = None


def _set_session_cookies(response: Response, user_id: str) -> str:
    csrf_token = secrets.token_urlsafe(32)
    secure = not settings.debug
    response.set_cookie(
        "teledrive_session",
        create_access_token(user_id),
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        "teledrive_csrf",
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    return csrf_token


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    response: Response,
    payload: AuthRequest,
    session: AsyncSession = Depends(get_db_session),
):
    if not await _registration_enabled(session):
        raise HTTPException(status_code=403, detail="Registration is disabled by the operator")
    existing = await session.scalar(select(UserModel).where(UserModel.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")

    first_user = await session.scalar(select(UserModel.id).limit(1))
    user = UserModel(
        id=str(uuid4()),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        is_operator=first_user is None,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    csrf_token = _set_session_cookies(response, user.id)
    return AuthResponse(
        access_token=create_access_token(user.id),
        user=_user_response(user),
        csrf_token=csrf_token,
    )


@router.post("/auth/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    payload: AuthRequest,
    session: AsyncSession = Depends(get_db_session),
):
    user = await session.scalar(select(UserModel).where(UserModel.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    csrf_token = _set_session_cookies(response, user.id)
    return AuthResponse(
        access_token=create_access_token(user.id),
        user=_user_response(user),
        csrf_token=csrf_token,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    response.delete_cookie("teledrive_session", path="/")
    response.delete_cookie("teledrive_csrf", path="/")
    response.status_code = status.HTTP_204_NO_CONTENT


@router.get("/auth/me", response_model=UserResponse)
async def me(user: UserModel = Depends(get_current_user)):
    return _user_response(user)


@router.get("/auth/registration-settings", response_model=RegistrationSettingsResponse)
async def get_registration_settings(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    _require_operator(user)
    return RegistrationSettingsResponse(registration_enabled=await _registration_enabled(session))


@router.put("/auth/registration-settings", response_model=RegistrationSettingsResponse)
@limiter.limit("10/minute")
async def update_registration_settings(
    request: Request,
    payload: RegistrationSettingsRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    _require_operator(user)
    setting = await session.get(AppSettingModel, "registration_enabled")
    if setting is None:
        setting = AppSettingModel(
            key="registration_enabled",
            bool_value=payload.registration_enabled,
        )
        session.add(setting)
    else:
        setting.bool_value = payload.registration_enabled
    await session.commit()
    return RegistrationSettingsResponse(registration_enabled=setting.bool_value)


@router.put("/auth/account", response_model=UserResponse)
async def update_account(
    payload: AccountUpdateRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.email is None and payload.new_password is None:
        raise HTTPException(status_code=400, detail="Enter a new email or password")

    if payload.email is not None:
        email = payload.email.lower()
        existing = await session.scalar(
            select(UserModel).where(UserModel.email == email, UserModel.id != user.id)
        )
        if existing:
            raise HTTPException(status_code=409, detail="Email is already registered")
        user.email = email
    if payload.new_password is not None:
        user.password_hash = hash_password(payload.new_password)

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_response(user)


@router.put("/auth/telegram-session", response_model=UserResponse)
async def save_telegram_session(
    payload: TelegramSessionRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    user.telegram_session_encrypted = encrypt_secret(payload.session)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_response(user)


@router.put("/auth/telegram-credentials", response_model=UserResponse)
async def save_telegram_credentials(
    payload: TelegramCredentialsRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    user.telegram_api_id_encrypted = encrypt_secret(payload.api_id.strip())
    user.telegram_api_hash_encrypted = encrypt_secret(payload.api_hash.strip())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_response(user)


@router.post("/auth/telegram-login/start", response_model=TelegramLoginResponse)
@limiter.limit("5/minute")
async def start_telegram_login(
    request: Request,
    payload: TelegramLoginStartRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    api_id, api_hash = _telegram_credentials(user)

    from telethon import TelegramClient
    from telethon.errors import ApiIdInvalidError, FloodWaitError, PhoneNumberInvalidError
    from telethon.sessions import StringSession

    phone = payload.phone.strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
        user.telegram_login_phone_encrypted = encrypt_secret(phone)
        user.telegram_login_code_hash_encrypted = encrypt_secret(sent_code.phone_code_hash)
        user.telegram_login_session_encrypted = encrypt_secret(client.session.save())
        session.add(user)
        await session.commit()
    except PhoneNumberInvalidError as error:
        raise HTTPException(status_code=400, detail="Telegram phone number is invalid.") from error
    except ApiIdInvalidError as error:
        raise HTTPException(status_code=400, detail="Telegram API ID or API Hash is invalid.") from error
    except FloodWaitError as error:
        raise HTTPException(
            status_code=429,
            detail=f"Telegram asks you to wait {error.seconds} seconds before trying again.",
        ) from error
    finally:
        await client.disconnect()

    return TelegramLoginResponse(
        next_step="code",
        message="Telegram sent a login code. Enter the OTP from your Telegram app.",
    )


@router.post("/auth/telegram-login/verify", response_model=TelegramLoginResponse)
@limiter.limit("10/minute")
async def verify_telegram_login(
    request: Request,
    payload: TelegramLoginVerifyRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    api_id, api_hash = _telegram_credentials(user)
    phone = decrypt_secret(user.telegram_login_phone_encrypted)
    phone_code_hash = decrypt_secret(user.telegram_login_code_hash_encrypted)
    pending_session = decrypt_secret(user.telegram_login_session_encrypted)
    if not pending_session:
        raise HTTPException(status_code=400, detail="Start Telegram login before verifying OTP.")

    from telethon import TelegramClient
    from telethon.errors import (
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
    )
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(pending_session), api_id, api_hash)
    try:
        await client.connect()
        if payload.password and not payload.code:
            await client.sign_in(password=payload.password)
        else:
            if not payload.code or not phone or not phone_code_hash:
                raise HTTPException(status_code=400, detail="Enter the Telegram OTP code.")
            try:
                await client.sign_in(
                    phone=phone,
                    code=payload.code.strip(),
                    phone_code_hash=phone_code_hash,
                )
            except SessionPasswordNeededError:
                user.telegram_login_session_encrypted = encrypt_secret(client.session.save())
                session.add(user)
                await session.commit()
                if not payload.password:
                    return TelegramLoginResponse(
                        next_step="password",
                        message="This Telegram account uses 2FA. Enter the Telegram cloud password.",
                    )
                await client.sign_in(password=payload.password)

        user.telegram_session_encrypted = encrypt_secret(client.session.save())
        _clear_pending_telegram_login(user)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except PhoneCodeInvalidError as error:
        raise HTTPException(status_code=400, detail="Telegram OTP code is invalid.") from error
    except PhoneCodeExpiredError as error:
        _clear_pending_telegram_login(user)
        session.add(user)
        await session.commit()
        raise HTTPException(status_code=400, detail="Telegram OTP code expired. Start login again.") from error
    except SessionPasswordNeededError as error:
        raise HTTPException(status_code=409, detail="Telegram 2FA password is required.") from error
    finally:
        await client.disconnect()

    return TelegramLoginResponse(
        next_step="done",
        message="Telegram login complete. Session saved securely.",
        user=_user_response(user),
    )
