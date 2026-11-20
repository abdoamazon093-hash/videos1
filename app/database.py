import sqlite3
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from app.config import settings

def get_db_path() -> Path:
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        raw_path = db_url.replace("sqlite:///", "")
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return path
    return Path(__file__).resolve().parent.parent / "cache.db"

def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                expires_at REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_store(expires_at)
        """)
        conn.commit()

def set_cache(key: str, value: str, ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
    now = time.time()
    expires_at = (now + ttl_seconds) if ttl_seconds else None
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cache_store (key, value, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at
        """, (key, value, now, now, expires_at))
        conn.commit()
    return {"key": key, "value": value, "expires_at": expires_at}

def get_cache(key: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT key, value, created_at, updated_at, expires_at
            FROM cache_store
            WHERE key = ?
        """, (key,))
        row = cur.fetchone()
        if not row:
            return None
        
        # Check TTL expiration
        if row["expires_at"] and row["expires_at"] < now:
            conn.execute("DELETE FROM cache_store WHERE key = ?", (key,))
            conn.commit()
            return None

        return {
            "key": row["key"],
            "value": row["value"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

def delete_cache(key: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM cache_store WHERE key = ?", (key,))
        conn.commit()
        return cur.rowcount > 0

def list_cache(limit: int = 50) -> List[Dict[str, Any]]:
    now = time.time()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT key, value, created_at, updated_at, expires_at
            FROM cache_store
            WHERE expires_at IS NULL OR expires_at >= ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (now, limit))
        rows = cur.fetchall()
        return [
            {
                "key": r["key"],
                "value": r["value"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "expires_at": r["expires_at"],
            }
            for r in rows
        ]

def get_stats() -> Dict[str, Any]:
    now = time.time()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM cache_store WHERE expires_at IS NULL OR expires_at >= ?", (now,))
        total = cur.fetchone()["total"]
        db_path = get_db_path()
        size_bytes = db_path.stat().st_size if db_path.exists() else 0
        return {
            "total_items": total,
            "db_size_bytes": size_bytes,
            "db_path": str(db_path.name),
        }
