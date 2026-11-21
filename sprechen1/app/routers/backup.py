from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BACKUPS_DIR, DB_PATH
from app.telegram_backup import send_backup_to_telegram, create_safe_sqlite_backup

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.post("")
async def trigger_backup():
    """
    Creates a consistent SQLite online backup compressed with gzip
    and sends it to Telegram if credentials are set.
    """
    try:
        result = await send_backup_to_telegram()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download")
def download_backup_gzip():
    """Generates an immediate safe SQLite online backup and serves it as a downloadable compressed file."""
    try:
        backup_file = create_safe_sqlite_backup()
        return FileResponse(
            path=str(backup_file),
            filename=backup_file.name,
            media_type="application/gzip"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {e}")


@router.get("/download-raw")
def download_raw_database():
    """Downloads the active sprechen.db SQLite database file directly."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")
    return FileResponse(
        path=str(DB_PATH),
        filename="sprechen.db",
        media_type="application/x-sqlite3"
    )


@router.get("/status")
def backup_status():
    backups = list(BACKUPS_DIR.glob("*.db.gz"))
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "total_backups": len(backups),
        "latest_backup": backups[0].name if backups else None,
        "latest_backup_size_kb": round(backups[0].stat().st_size / 1024, 2) if backups else 0
    }
