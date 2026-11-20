import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.database import (
    init_db,
    set_cache,
    get_cache,
    delete_cache,
    list_cache,
    get_stats,
)

START_TIME = time.time()
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite cache on startup
    init_db()
    yield

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Clean Backend with FastAPI & Local SQLite Cache",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CacheSetRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=256, description="Cache key identifier")
    value: str = Field(..., description="Cache value (string or JSON string)")
    ttl_seconds: Optional[int] = Field(None, ge=1, description="Optional time-to-live in seconds")

# API Routes
@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    uptime_seconds = int(time.time() - START_TIME)
    try:
        stats = get_stats()
        db_status = "healthy"
    except Exception as e:
        stats = {"error": str(e)}
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "uptime_seconds": uptime_seconds,
        "database": {
            "engine": "SQLite",
            "status": db_status,
            **stats,
        },
    }

@app.get("/api/info")
def app_info() -> Dict[str, Any]:
    return {
        "app_name": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
        "host": settings.host,
        "port": settings.port,
        "system_status": "active 24/7",
    }

@app.get("/api/cache", response_model=List[Dict[str, Any]])
def api_list_cache(limit: int = 50):
    return list_cache(limit=limit)

@app.post("/api/cache", status_code=status.HTTP_201_CREATED)
def api_set_cache(payload: CacheSetRequest):
    return set_cache(key=payload.key, value=payload.value, ttl_seconds=payload.ttl_seconds)

@app.get("/api/cache/{key}")
def api_get_cache(key: str):
    item = get_cache(key)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key '{key}' not found or expired",
        )
    return item

@app.delete("/api/cache/{key}")
def api_delete_cache(key: str):
    deleted = delete_cache(key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key '{key}' not found",
        )
    return {"success": True, "deleted_key": key}

# Mount static folder and serve frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": f"{settings.app_name} API is running."}
