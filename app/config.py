import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "Videos1"
    app_env: str = "production"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8095
    secret_key: str = "default-insecure-secret"
    api_key: str = ""
    database_url: str = "sqlite:///./cache.db"

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
