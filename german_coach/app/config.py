import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# Gemini Configuration
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

# Telegram Configuration
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Database Configuration
_raw_db_path = os.getenv("DB_PATH", "data/german_coach.db").strip()
if os.path.isabs(_raw_db_path):
    DB_PATH = Path(_raw_db_path)
else:
    DB_PATH = BASE_DIR / _raw_db_path

# Backups Directory
BACKUPS_DIR = BASE_DIR / "backups"


def get_env_status() -> dict:
    """Returns the presence status of sensitive configurations without exposing values."""
    return {
        "gemini_api_key_configured": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "telegram_bot_token_configured": bool(TELEGRAM_BOT_TOKEN),
        "telegram_chat_id_configured": bool(TELEGRAM_CHAT_ID),
        "db_path": str(DB_PATH),
    }
