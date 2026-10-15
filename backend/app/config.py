import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "FIR-Sahayak"
    APP_ENV: str = "development"
    SECRET_KEY: str = "supersecretjwtkey_ap_excise_secure_fir_sahayak_2024"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Supabase Cloud Database & Storage
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL", None)
    SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY", None)
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY", None)
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "evidence")
    SUPABASE_DATABASE_URL: Optional[str] = os.getenv("SUPABASE_DATABASE_URL", None)

    # Database URLs (falls back to local SQLite if Supabase PostgreSQL is not set)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///C:/Users/LENOVO/Desktop/FIR-Sahayak/data/fir_sahayak.db"
    )
    SYNC_DATABASE_URL: str = os.getenv(
        "SYNC_DATABASE_URL",
        "sqlite:///C:/Users/LENOVO/Desktop/FIR-Sahayak/data/fir_sahayak.db"
    )

    # Storage paths
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    EVIDENCE_DIR: str = os.path.join(BASE_DIR, "data", "evidence")
    EXPORTS_DIR: str = os.path.join(BASE_DIR, "data", "exports")
    BACKUPS_DIR: str = os.path.join(BASE_DIR, "data", "backups")
    CORPUS_DIR: str = os.path.join(BASE_DIR, "corpus")

    # AI integration
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    GEMINI_TEXT_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"

    DEMO_MODE: bool = True
    ALLOW_SYNTHETIC_DATA: bool = True

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        extra = "ignore"

settings = Settings()
os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)
os.makedirs(settings.EXPORTS_DIR, exist_ok=True)
os.makedirs(settings.BACKUPS_DIR, exist_ok=True)
os.makedirs(settings.CORPUS_DIR, exist_ok=True)
