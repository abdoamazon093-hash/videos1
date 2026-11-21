import gzip
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import httpx

from app.config import (
    BACKUPS_DIR,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from app.db import get_db_path, init_db

logger = logging.getLogger(__name__)


class TelegramBackupError(Exception):
    """Raised when Telegram backup cannot proceed or fails."""
    pass


class TelegramConfigMissingError(TelegramBackupError):
    """Raised when Telegram credentials are not configured."""
    pass


def create_safe_sqlite_backup() -> Path:
    """
    Creates a consistent SQLite backup safely using SQLite Online Backup API,
    then compresses it with gzip into the backups directory.
    """
    db_file = get_db_path()
    if not db_file.exists():
        init_db()

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_raw_backup = BACKUPS_DIR / f"vocab_tutor_{timestamp_str}.raw.db"
    final_gz_backup = BACKUPS_DIR / f"vocab_tutor_{timestamp_str}.db.gz"

    try:
        # Perform safe online backup
        source_conn = sqlite3.connect(str(db_file), timeout=15.0)
        dest_conn = sqlite3.connect(str(temp_raw_backup))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        # Compress with gzip level 9
        with open(temp_raw_backup, "rb") as f_in:
            with gzip.open(final_gz_backup, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        return final_gz_backup
    finally:
        if temp_raw_backup.exists():
            try:
                temp_raw_backup.unlink()
            except OSError:
                pass


async def send_backup_to_telegram() -> Dict[str, Any]:
    """
    Backs up the SQLite database and sends the compressed archive to Telegram.
    Raises TelegramConfigMissingError if credentials are not configured.
    """
    # 1. Create the compressed database backup
    backup_path = create_safe_sqlite_backup()
    file_size_bytes = backup_path.stat().st_size
    file_size_kb = round(file_size_bytes / 1024, 2)
    timestamp_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        # Return success for local backup but note missing telegram
        return {
            "status": "local_only",
            "message": "Local compressed backup created. Telegram credentials not configured in .env.",
            "backup_file": backup_path.name,
            "size_kb": file_size_kb,
            "timestamp": timestamp_display,
        }

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    caption = (
        f"🇩🇪 *Vocab Tutor - Database Backup*\n"
        f"📅 *Timestamp:* `{timestamp_display}`\n"
        f"📦 *File:* `{backup_path.name}`\n"
        f"📊 *Size:* `{file_size_kb} KB`"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(backup_path, "rb") as f:
                files = {
                    "document": (backup_path.name, f, "application/gzip")
                }
                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "Markdown",
                }
                response = await client.post(telegram_url, data=data, files=files)

        if response.status_code != 200:
            logger.error(f"Telegram API responded with error: {response.text}")
            raise TelegramBackupError(
                f"Telegram API returned status {response.status_code}: {response.text}"
            )

        resp_json = response.json()
        if not resp_json.get("ok"):
            raise TelegramBackupError(f"Telegram API failure: {resp_json}")

        return {
            "status": "success",
            "message": "Backup created and sent to Telegram successfully.",
            "backup_file": backup_path.name,
            "size_kb": file_size_kb,
            "timestamp": timestamp_display,
        }

    except httpx.RequestError as req_err:
        logger.error(f"Network error sending backup to Telegram: {req_err}")
        raise TelegramBackupError(f"Network error sending backup to Telegram: {str(req_err)}") from req_err
