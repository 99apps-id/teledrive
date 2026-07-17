from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __app_name__, __version__
from app.api.auth import router as auth_router
from app.api.files import create_files_router
from app.api.server_files import router as server_files_router
from app.api.storage import create_storage_router
from app.api.system import router as system_router
from app.api.webdav import router as webdav_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.rate_limit import limiter
from app.services.telegram_private_channel import TelegramPrivateChannelStorage

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = time.time()
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=__app_name__,
    version=__version__,
    description="API-first self-hosted file manager using a user's Telegram private channel as storage.",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "PROPFIND", "MKCOL", "MOVE", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID", "Depth", "Destination", "Overwrite"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"} and request.url.path.endswith("/upload"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.teledrive_max_upload_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Upload exceeds the {settings.teledrive_max_upload_bytes} byte limit"},
            )
    return await call_next(request)


storage = TelegramPrivateChannelStorage()

app.include_router(auth_router, prefix="/api")
app.include_router(create_files_router(storage), prefix="/api")
app.include_router(server_files_router, prefix="/api")
app.include_router(create_storage_router(storage), prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(webdav_router, prefix="/dav")


@app.get("/health", tags=["System"])
async def health_check(request: Request):
    started_at = getattr(request.app.state, "started_at", time.time())
    return {
        "status": "ok",
        "version": __version__,
        "app": __app_name__,
        "uptime_seconds": round(time.time() - started_at, 2),
    }


@app.get("/api/health", tags=["System"])
async def api_health_check():
    return {"data": {"ok": True, "service": "teledrive-api"}}
