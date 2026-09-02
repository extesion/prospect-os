from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from pathlib import Path

# Ensure .env is read into os.environ
def _load_env_to_environ():
    for env_file in [Path(".env"), Path("backend/.env")]:
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass

_load_env_to_environ()

class Settings(BaseSettings):
    PROJECT_NAME: str = "PROSPECT OS"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api"
    
    # Database
    # Default to PostgreSQL, with fallback capability
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/youtube_prospector"
    )
    
    # JWT & Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "prospector-super-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS (Extension & Web)
    CORS_ORIGINS: List[str] = [
        "*",  # Allow all for Chrome extensions & dev
    ]
    
    # Dashboard URL (config for extension)
    DASHBOARD_URL: str = os.getenv("DASHBOARD_URL", "https://prospect-os-seven.vercel.app/dashboard")

    # YouTube API
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
