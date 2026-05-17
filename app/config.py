from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Цукиба"
    database_url: str = "sqlite:///./assets/database.db"
    redis_url: str = "redis://localhost:6379/0"
    manage_key: str = "secretkey"
    timezone: str = "Europe/Moscow"
    assets_dir: Path = Path("assets")
    templates_dir: Path = Path("app/templates")
    media_dir: Path = Path("media")
    thumb_dir: Path = Path("thumb")
    captcha_ttl_seconds: int = 3600
    captcha_secret: str = "change-this-secret"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
