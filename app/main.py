import os
import sys
import time
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

logger = logging.getLogger("unified_platform")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SPRECHEN_DIR = BASE_DIR / "sprechen1"
COACH_DIR = BASE_DIR / "german_coach"

VOCAB_URL = os.getenv("VOCAB_TUTOR_URL", "http://127.0.0.1:8085")
COACH_URL = os.getenv("GERMAN_COACH_URL", "http://127.0.0.1:8000")

# Global HTTP client for connection pooling
http_client: Optional[httpx.AsyncClient] = None
child_processes: List[asyncio.subprocess.Process] = []

async def check_service(url: str, path: str = "/health") -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(f"{url}{path}")
            return res.status_code in (200, 404)
    except Exception:
        return False

async def ensure_service_running(name: str, port: int, work_dir: Path, check_path: str = "/"):
    url = f"http://127.0.0.1:{port}"
    if await check_service(url, check_path):
        logger.info(f"Service {name} is already running on {url}")
        return

    logger.info(f"Service {name} not detected on port {port}. Spawning internal worker...")
    py_bin = sys.executable
    proc = await asyncio.create_subprocess_exec(
        py_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
        cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    child_processes.append(proc)
    
    # Wait up to 5 seconds for service to bind
    for _ in range(25):
        await asyncio.sleep(0.2)
        if await check_service(url, check_path):
            logger.info(f"Service {name} successfully started and ready on {url}")
            return
    logger.warning(f"Service {name} process started (PID {proc.pid}) but did not respond to health check in time.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=90.0, limits=httpx.Limits(max_keepalive_connections=50, max_connections=100))
    
    # Ensure both underlying services are running
    await ensure_service_running("sprechen1_vocab_tutor", 8085, SPRECHEN_DIR, "/health")
    await ensure_service_running("german_coach", 8000, COACH_DIR, "/api/health")

    yield

    # Shutdown
    if http_client:
        await http_client.aclose()
    for proc in child_processes:
        try:
            proc.terminate()
            await proc.wait()
        except Exception:
            pass

app = FastAPI(
    title="German Unified Platform | المنصة الألمانية المتكاملة",
    description="Unified platform integrating Vocab Tutor (sprechen1 v16) and German Coach (v18).",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper for generic reverse proxying
async def forward_request(target_base: str, request: Request, custom_path: Optional[str] = None) -> Response:
    global http_client
    if not http_client:
        http_client = httpx.AsyncClient(timeout=90.0)

    path = custom_path if custom_path is not None else request.url.path
    url = f"{target_base}{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    try:
        body = await request.body()
        resp = await http_client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

        response_headers = dict(resp.headers)
        response_headers.pop("content-length", None)
        response_headers.pop("content-encoding", None)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception as e:
        logger.error(f"Error proxying {request.method} {url}: {e}")
        return JSONResponse(
            {"error": "Upstream service unreachable", "details": str(e), "target": target_base},
            status_code=status.HTTP_502_BAD_GATEWAY
        )

# ============================================================================
# Front-end Direct Views & Static Assets
# ============================================================================

@app.api_route("/vocab", methods=["GET", "HEAD"], response_class=FileResponse)
@app.api_route("/vocab/", methods=["GET", "HEAD"], response_class=FileResponse)
def serve_vocab():
    index_file = SPRECHEN_DIR / "app" / "static" / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
    raise HTTPException(status_code=404, detail="Vocab Tutor index.html not found.")

@app.api_route("/coach", methods=["GET", "HEAD"], response_class=FileResponse)
@app.api_route("/coach/", methods=["GET", "HEAD"], response_class=FileResponse)
def serve_coach():
    index_file = COACH_DIR / "app" / "static" / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    raise HTTPException(status_code=404, detail="German Coach index.html not found.")

@app.api_route("/static/styles.css", methods=["GET", "HEAD"])
def serve_coach_css():
    css_file = COACH_DIR / "app" / "static" / "styles.css"
    if css_file.exists():
        return FileResponse(
            css_file,
            media_type="text/css",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return Response(status_code=404)

@app.api_route("/static/app.js", methods=["GET", "HEAD"])
def serve_coach_js():
    js_file = COACH_DIR / "app" / "static" / "app.js"
    if js_file.exists():
        return FileResponse(
            js_file,
            media_type="application/javascript",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return Response(status_code=404)

# Static files for unified hub
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_unified_portal():
    hub_file = STATIC_DIR / "index.html"
    if hub_file.exists():
        return FileResponse(hub_file)
    return {"message": "German Unified Platform is running."}

# ============================================================================
# API Routing: Vocab Tutor (sprechen1 v16)
# ============================================================================

@app.api_route("/api/documents{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_documents(path: str, request: Request):
    return await forward_request(VOCAB_URL, request)

@app.api_route("/api/words{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_words(path: str, request: Request):
    return await forward_request(VOCAB_URL, request)

@app.api_route("/api/upload{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_upload(path: str, request: Request):
    return await forward_request(VOCAB_URL, request)

@app.api_route("/api/export{path:path}", methods=["GET", "OPTIONS"])
async def proxy_export(path: str, request: Request):
    return await forward_request(VOCAB_URL, request)

@app.get("/api/version")
async def get_version(request: Request):
    # Proxy to vocab version or return unified version info
    return {
        "platform": "Unified Deutsch Platform",
        "vocab_tutor_version": "v16",
        "german_coach_version": "v18",
        "current_tag": "v2"
    }

# ============================================================================
# API Routing: German Coach (v18)
# ============================================================================

@app.api_route("/api/correct", methods=["POST", "OPTIONS"])
async def proxy_correct(request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/word", methods=["POST", "OPTIONS"])
async def proxy_word(request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/ask", methods=["POST", "OPTIONS"])
async def proxy_ask(request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/turns{path:path}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy_turns(path: str, request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/clips{path:path}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy_clips(path: str, request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/history", methods=["GET", "OPTIONS"])
async def proxy_history(request: Request):
    return await forward_request(COACH_URL, request)

@app.api_route("/api/radar", methods=["GET", "OPTIONS"])
async def proxy_radar(request: Request):
    return await forward_request(COACH_URL, request)

# ============================================================================
# Shared / System Endpoints
# ============================================================================

@app.post("/api/backup/telegram")
async def proxy_telegram_backup(request: Request):
    # First try coach backup then vocab backup
    res1 = await forward_request(COACH_URL, request)
    res2 = await forward_request(VOCAB_URL, request)
    return {
        "status": "success",
        "german_coach_backup": res1.status_code == 200,
        "vocab_tutor_backup": res2.status_code == 200,
    }

@app.get("/api/backup/download")
@app.get("/api/backup/download-raw")
async def proxy_backup_download(request: Request):
    return await forward_request(VOCAB_URL, request)

@app.get("/health")
def simple_health():
    return {
        "status": "ok",
        "platform": "Unified Deutsch Platform",
        "integrated_apps": ["Vocab Tutor v16", "German Coach v18"],
    }

@app.get("/api/health")
async def comprehensive_health():
    vocab_ok = await check_service(VOCAB_URL, "/health")
    coach_ok = await check_service(COACH_URL, "/api/health")
    return {
        "status": "healthy" if (vocab_ok and coach_ok) else "degraded",
        "platform": "Unified Deutsch Platform",
        "port": settings.port,
        "vocab_tutor": {
            "name": "Vocab Tutor (sprechen1)",
            "version": "v16",
            "url": VOCAB_URL,
            "status": "healthy" if vocab_ok else "unreachable"
        },
        "german_coach": {
            "name": "German Coach",
            "version": "v18",
            "url": COACH_URL,
            "status": "healthy" if coach_ok else "unreachable"
        }
    }
