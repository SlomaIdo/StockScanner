from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (prefix ``SS_``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="SS_", env_file=".env", extra="ignore")

    app_name: str = "StockScanner"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://stockscanner:stockscanner@localhost:5432/stockscanner"
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
