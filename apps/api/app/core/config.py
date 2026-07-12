from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"
    database_url: str = "sqlite+aiosqlite:///./teledrive.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_temp_path: str = "./storage"
    jwt_secret: str = "change-me-in-production"
    encryption_key: str = "change-me-in-production"
    jwt_expire_minutes: int = 480
    teledrive_registration_enabled: bool | None = None
    teledrive_max_upload_bytes: int = 1024 * 1024 * 1024
    teledrive_max_archive_bytes: int = 2 * 1024 * 1024 * 1024

    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_session: str = ""
    teledrive_storage_channel: str = "TeleDrive Storage"

    teledrive_server_files_mode: str = "local"
    teledrive_server_files_root: str = "./server-files"
    teledrive_server_files_sftp_host: str = ""
    teledrive_server_files_sftp_port: int = 22
    teledrive_server_files_sftp_user: str = ""
    teledrive_server_files_sftp_password: str = ""
    teledrive_server_files_sftp_key_path: str = ""
    teledrive_server_files_sftp_root: str = "/home/admin"
    teledrive_server_files_sftp_allow_unknown_hosts: bool = False
    teledrive_update_check_enabled: bool = True
    teledrive_releases_api_url: str = (
        "https://api.github.com/repos/99apps-id/teledrive/releases/latest"
    )

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def debug(self) -> bool:
        return self.app_env != "production"

    @property
    def registration_enabled(self) -> bool:
        if self.teledrive_registration_enabled is not None:
            return self.teledrive_registration_enabled
        return self.debug

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env.lower().strip() != "production":
            return self
        weak_values = {"", "change-me-in-production", "change-this-to-a-long-random-secret"}
        if self.jwt_secret in weak_values or len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be set to a strong secret in production")
        if self.encryption_key in weak_values or len(self.encryption_key) < 32:
            raise ValueError("ENCRYPTION_KEY must be set to a strong secret in production")
        if self.jwt_expire_minutes < 5:
            raise ValueError("JWT_EXPIRE_MINUTES must be at least 5 in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
