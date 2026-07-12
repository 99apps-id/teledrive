import secrets

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import decode_access_token
from app.models.user import UserModel

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session_cookie: str | None = Cookie(default=None, alias="teledrive_session"),
    csrf_cookie: str | None = Cookie(default=None, alias="teledrive_csrf"),
    session: AsyncSession = Depends(get_db_session),
) -> UserModel:
    token = credentials.credentials if credentials is not None else session_cookie
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    user = await session.get(UserModel, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if credentials is None and request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token is missing or invalid",
            )
    return user
