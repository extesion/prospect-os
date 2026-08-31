from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "YouTube Prospector API"
    VERSION: str = "1.0.0"
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
    DASHBOARD_URL: str = os.getenv("DASHBOARD_URL", "http://localhost:8000/dashboard")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
