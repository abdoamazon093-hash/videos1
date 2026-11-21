import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import BASE_DIR, HOST, PORT
from app.db import init_db
from app.services.seeder import seed_werkstatt_b2
from app.routers import upload, documents, vocab, export, backup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vocab_tutor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Vocab Tutor application...")
    init_db()
    seeded = seed_werkstatt_b2()
    logger.info(f"Database ready with {seeded} initial seed words.")
    yield
    # Shutdown
    logger.info("Shutting down Vocab Tutor...")


app = FastAPI(
    title="Vocab Tutor B2/C1 - Interactive Dictionary Platform",
    description="Intelligent vocabulary extraction, audio pronunciation, Perfekt conjugations, and standalone export.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(upload.router)
app.include_router(documents.router)
app.include_router(vocab.router)
app.include_router(export.router)
app.include_router(backup.router)

# Static files
STATIC_DIR = BASE_DIR / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"message": "Vocab Tutor API is running. UI index.html not yet built."}


@app.get("/api/version")
def get_version():
    import subprocess
    try:
        tag = subprocess.check_output(["git", "describe", "--tags", "--abbrev=0"], text=True, cwd=str(BASE_DIR)).strip()
    except Exception:
        tag = "v14"
    return {"version": tag}


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "vocab_tutor"}
