from pydantic import BaseModel, EmailStr, Field


class AuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_operator: bool
    has_telegram_api_credentials: bool
    has_telegram_session: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str
    user: UserResponse


class AccountUpdateRequest(BaseModel):
    current_password: str = Field(min_length=8)
    email: EmailStr | None = None
    new_password: str | None = Field(default=None, min_length=8)


class RegistrationSettingsResponse(BaseModel):
    registration_enabled: bool


class RegistrationSettingsRequest(BaseModel):
    registration_enabled: bool


class TelegramSessionRequest(BaseModel):
    session: str = Field(min_length=8)


class TelegramCredentialsRequest(BaseModel):
    api_id: str = Field(min_length=4)
    api_hash: str = Field(min_length=20)


class TelegramLoginStartRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=32)


class TelegramLoginVerifyRequest(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=32)
    password: str | None = Field(default=None, min_length=1, max_length=256)


class TelegramLoginResponse(BaseModel):
    next_step: str
    message: str
    user: UserResponse | None = None
