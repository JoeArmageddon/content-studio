"""
Central settings for Content Studio.

Loaded from environment variables / a .env file at the backend root.
All third-party keys default to None so the app can boot with stub agents
(Milestone 1) before any real credentials exist.
"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # Core
    database_url: str = f"sqlite:///{DATA_DIR / 'content_studio.db'}"
    scheduler_enabled: bool = False
    scheduler_start_hour: int = 8  # UTC hour the first daily run window opens per channel

    # Reddit (Sourcing Agent — Milestone 2)
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    reddit_user_agent: str = "ContentStudioBot/0.1"

    # LLMs (Hook/Scriptwriter/Script QA agents — Milestone 3)
    groq_api_key: Optional[str] = None
    # Groq retires models without much warning (llama-3.3-70b-versatile was
    # gone by Nov 2026) — configurable via GROQ_MODEL so a retirement is an
    # env-var change, not a code change.
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: Optional[str] = None

    # Voice (Voice Agent — Milestone 4). Kokoro (local, free, no key) is the
    # engine — model files are downloaded once into DATA_DIR/models/kokoro/
    # (see README's Kokoro setup section), not committed to git.
    kokoro_model_path: str = str(DATA_DIR / "models" / "kokoro" / "kokoro-v1.0.onnx")
    kokoro_voices_path: str = str(DATA_DIR / "models" / "kokoro" / "voices-v1.0.bin")
    elevenlabs_api_key: Optional[str] = None  # manual "hero video" opt-in only, not wired

    # Background footage (Background-Sourcing Agent — Milestone 5)
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    youtube_data_api_key: Optional[str] = None  # for CC-licensed search + competitor scan

    # YouTube upload + analytics (Publisher/Feedback agents — Milestone 6/8)
    youtube_oauth_client_secrets_path: Optional[str] = None


settings = Settings()

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only filesystem (e.g. Vercel's serverless functions, which only
    # this module's importers actually need — the thin dashboard API never
    # touches local files/Kokoro/SQLite, just DATABASE_URL). Not fatal.
    pass
