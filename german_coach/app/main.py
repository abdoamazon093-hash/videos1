import asyncio
import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import BASE_DIR, get_env_status
from app.db import (
    bulk_import_clips,
    bulk_insert_turns,
    check_db_health,
    clear_ai_chat,
    clear_clips,
    clear_turns,
    delete_clip,
    delete_turn,
    get_ai_chat,
    get_cached_correction,
    get_cached_word,
    get_clip_by_id,
    get_clips,
    get_history,
    get_radar_stats,
    get_turns,
    init_db,
    normalize_cache_key,
    save_ai_chat,
    save_clip,
    save_correction,
    save_turn,
    set_cached_correction,
    set_cached_word,
    update_clip,
)
from app.gemini_service import (
    GeminiKeyMissingError,
    GeminiServiceError,
    ask_assistant,
    correct_sentence,
    explain_clip,
    explain_word,
)
from app.telegram_backup import (
    TelegramBackupError,
    TelegramConfigMissingError,
    send_backup_to_telegram,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure SQLite database and all tables exist
    init_db()
    yield


app = FastAPI(
    title="German Coach API",
    description="Contextual German Corrector (B1–C2) with Arabic Translation, SQLite Caching, Smart Clips, & Grammar Error Radar",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files & Frontend Routing
STATIC_DIR = BASE_DIR / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(str(index_file))


# ============================================================================
# Request / Response Schemas
# ============================================================================

class CorrectionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="German sentence to correct (can contain embedded Arabic words).")
    level: str = Field(default="B2", pattern="^(B1|B2|C1|C2|b1|b2|c1|c2)$", description="Target CEFR level.")
    force_refresh: bool = Field(default=False, description="Whether to bypass SQLite cache and force a new AI generation.")


class WordRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=100, description="German word to lookup.")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="Question for the German assistant.")
    current_sentence: Optional[str] = Field(default=None, max_length=2000, description="Optional sentence context.")


class TurnCreateRequest(BaseModel):
    user_sentence: str = Field(..., min_length=1)
    corrected_german: str = Field(..., min_length=1)
    arabic_meaning: Optional[str] = ""
    is_correct: bool = False
    summary_ar: Optional[str] = ""


class TurnBulkRequest(BaseModel):
    turns: List[Dict[str, Any]] = Field(..., description="List of turns to restore.")


class ClipCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="German phrase or word to save in clips.")
    arabic_meaning: Optional[str] = ""
    label: Optional[str] = ""
    grammar_explanation: Optional[str] = ""
    examples: Optional[List[Dict[str, str]]] = None
    synonyms: Optional[List[str]] = None
    is_open: bool = False


class ClipImportRequest(BaseModel):
    clips: List[Dict[str, Any]] = Field(..., description="List of clips to import.")


class HealthResponse(BaseModel):
    status: str
    database: str
    environment: Dict[str, Any]


# ============================================================================
# System Endpoints
# ============================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Returns server and database health, along with configuration status without leaking secret values."""
    db_ok = check_db_health()
    env_info = get_env_status()

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "environment": env_info,
    }


# ============================================================================
# Section 1 & 2: Correction & Caching
# ============================================================================

@app.post("/api/correct", status_code=status.HTTP_200_OK, tags=["Correction"])
async def correct_endpoint(payload: CorrectionRequest):
    """
    Corrects a German sentence with sub-5ms SQLite caching,
    translates embedded Arabic words, outputs replacements & radar rules,
    and updates error radar statistics.
    """
    clean_text = payload.text.strip()
    target_level = payload.level.upper()
    cache_key = normalize_cache_key(clean_text, target_level)

    t_start = time.perf_counter()

    # 1. Check SQLite Cache first (unless force_refresh is requested)
    if not payload.force_refresh:
        cached_result = get_cached_correction(cache_key)
        if cached_result:
            elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
            cached_result["cached"] = True
            cached_result["elapsed_ms"] = elapsed_ms
            return cached_result

    # 2. Call Gemini API for live analysis
    try:
        ai_result = await asyncio.to_thread(correct_sentence, text=clean_text, level=target_level)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

        # 3. Persist to SQLite History & Radar Error Logs
        saved_record = save_correction(
            original_text=ai_result["original_text"],
            corrected_text=ai_result["corrected_text"],
            level=ai_result["level"],
            explanation=ai_result.get("explanation", ""),
            arabic_translations=ai_result.get("arabic_translations", []),
            diff_data=ai_result.get("diff_data", []),
            contextual_examples=ai_result.get("contextual_examples", []),
            errors=ai_result.get("errors", []),
        )

        response_payload = {
            **ai_result,
            "id": saved_record["id"],
            "cached": False,
            "elapsed_ms": elapsed_ms,
            "created_at": saved_record["created_at"],
        }

        # 4. Store in SQLite Cache for subsequent instant calls
        set_cached_correction(cache_key, target_level, response_payload)

        return response_payload

    except GeminiKeyMissingError as kme:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(kme),
        )
    except GeminiServiceError as gse:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI Correction Service Error: {str(gse)}",
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected server error: {str(e)}",
        )


# ============================================================================
# Section 2: Word Meaning Lookup & Caching
# ============================================================================

@app.post("/api/word", tags=["Dictionary"])
async def word_lookup_endpoint(payload: WordRequest):
    """
    Looks up a German word meaning, article, and examples with SQLite caching.
    """
    clean_word = payload.word.strip()
    t_start = time.perf_counter()

    # Check cache
    cached = get_cached_word(clean_word)
    if cached:
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return {**cached, "cached": True, "elapsed_ms": elapsed_ms}

    try:
        data = await asyncio.to_thread(explain_word, clean_word)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

        saved = set_cached_word(
            word=data["word"],
            german_word=data["german_word"],
            arabic_meaning=data["arabic_meaning"],
            examples=data.get("examples", []),
        )
        return {**saved, "cached": False, "elapsed_ms": elapsed_ms}

    except GeminiKeyMissingError as kme:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(kme))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Word lookup error: {str(e)}")


# ============================================================================
# Section 3: AI Assistant (Grammar & Sentence Q&A)
# ============================================================================

@app.post("/api/ask", tags=["Assistant"])
async def ask_endpoint(payload: AskRequest):
    """Answers a grammar or contextual question concisely and saves it in chat history."""
    try:
        ai_resp = await asyncio.to_thread(
            ask_assistant,
            question=payload.question,
            current_sentence=payload.current_sentence,
        )
        saved = save_ai_chat(
            question=ai_resp["question"],
            answer_ar=ai_resp["answer_ar"],
            german_highlight=ai_resp.get("german_highlight", ""),
            examples=ai_resp.get("examples", []),
        )
        return saved
    except GeminiKeyMissingError as kme:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(kme))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Assistant error: {str(e)}")


@app.get("/api/ask/history", tags=["Assistant"])
async def ask_history_endpoint(limit: int = Query(default=20, ge=1, le=100)):
    """Retrieves recent AI Assistant Q&A history."""
    return get_ai_chat(limit=limit)


@app.delete("/api/ask/history", tags=["Assistant"])
async def clear_ask_history_endpoint():
    """Clears AI Assistant chat history."""
    count = clear_ai_chat()
    return {"status": "success", "cleared_count": count}


# ============================================================================
# Section 3: Conversation Turns (Session Management)
# ============================================================================

@app.get("/api/turns", tags=["Turns"])
async def get_turns_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Retrieves saved conversation turns."""
    items = get_turns(limit=limit, offset=offset)
    return {"total": len(items), "items": items}


@app.post("/api/turns", tags=["Turns"])
async def create_turn_endpoint(payload: TurnCreateRequest):
    """Saves a single conversation turn."""
    saved = save_turn(
        user_sentence=payload.user_sentence,
        corrected_german=payload.corrected_german,
        arabic_meaning=payload.arabic_meaning,
        is_correct=payload.is_correct,
        summary_ar=payload.summary_ar,
    )
    return saved


@app.delete("/api/turns/{turn_id}", tags=["Turns"])
async def delete_turn_endpoint(turn_id: int = Path(..., ge=1)):
    """Deletes a single turn by id."""
    deleted = delete_turn(turn_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Turn not found")
    return {"status": "success", "deleted_id": turn_id}


@app.delete("/api/turns", tags=["Turns"])
async def clear_turns_endpoint():
    """Clears all conversation turns."""
    count = clear_turns()
    return {"status": "success", "cleared_count": count}


@app.post("/api/turns/bulk", tags=["Turns"])
async def bulk_turns_endpoint(payload: TurnBulkRequest):
    """Restores a list of turns (used for Undo functionality)."""
    inserted = bulk_insert_turns(payload.turns)
    return {"status": "success", "inserted_count": len(inserted), "items": inserted}


# ============================================================================
# Section 6: Smart Clips (Clipboard Management)
# ============================================================================

@app.get("/api/clips", tags=["Clips"])
async def get_clips_endpoint():
    """Retrieves all saved smart clips."""
    clips = get_clips()
    return {"total": len(clips), "items": clips}


@app.post("/api/clips", tags=["Clips"])
async def create_clip_endpoint(payload: ClipCreateRequest):
    """Saves or updates a smart clip by text, automatically fetching AI Arabic translation and context if missing."""
    clean_text = payload.text.strip()
    arabic_meaning = (payload.arabic_meaning or "").strip()
    grammar_explanation = (payload.grammar_explanation or "").strip()
    examples = payload.examples or []
    synonyms = payload.synonyms or []

    # If Arabic translation is missing, auto-fetch via AI (or word cache for single words)
    if not arabic_meaning:
        # 1. Quick check in word meanings cache if it's a single word
        if " " not in clean_text:
            cached = get_cached_word(clean_text)
            if cached and cached.get("arabic_meaning"):
                arabic_meaning = cached["arabic_meaning"]
                if not examples and cached.get("examples"):
                    examples = cached["examples"]

        # 2. Call Gemini AI via explain_clip if still no translation
        if not arabic_meaning:
            try:
                analysis = await asyncio.to_thread(explain_clip, clean_text)
                if analysis.get("arabic_translation"):
                    arabic_meaning = analysis["arabic_translation"]
                if not grammar_explanation and analysis.get("grammar_explanation"):
                    grammar_explanation = analysis["grammar_explanation"]
                if not synonyms and analysis.get("synonyms"):
                    synonyms = analysis["synonyms"]
                if not examples and analysis.get("examples"):
                    examples = analysis["examples"]
            except Exception as e:
                logger.warning(f"Auto-translate clip failed for '{clean_text}': {e}")

    saved = save_clip(
        text=clean_text,
        arabic_meaning=arabic_meaning,
        label=payload.label,
        grammar_explanation=grammar_explanation,
        examples=examples,
        synonyms=synonyms,
        is_open=payload.is_open,
    )
    return saved


@app.post("/api/clips/{clip_id}/explain", tags=["Clips"])
async def explain_clip_endpoint(clip_id: int = Path(..., ge=1)):
    """Analyzes a saved clip with Gemini, adding grammar explanation, synonyms, and examples."""
    clip = get_clip_by_id(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        analysis = await asyncio.to_thread(explain_clip, clip["text"])
        updated = update_clip(
            clip_id=clip_id,
            arabic_meaning=analysis.get("arabic_translation") or clip["arabic_meaning"],
            grammar_explanation=analysis.get("grammar_explanation") or clip["grammar_explanation"],
            synonyms=analysis.get("synonyms") or clip["synonyms"],
            examples=analysis.get("examples") or clip["examples"],
        )
        return updated
    except GeminiKeyMissingError as kme:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(kme))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Explain clip error: {str(e)}")


@app.delete("/api/clips/{clip_id}", tags=["Clips"])
async def delete_clip_endpoint(clip_id: int = Path(..., ge=1)):
    """Deletes a clip by id."""
    deleted = delete_clip(clip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {"status": "success", "deleted_id": clip_id}


@app.delete("/api/clips", tags=["Clips"])
async def clear_clips_endpoint():
    """Clears all smart clips."""
    count = clear_clips()
    return {"status": "success", "cleared_count": count}


@app.post("/api/clips/import", tags=["Clips"])
async def import_clips_endpoint(payload: ClipImportRequest):
    """Imports or merges a JSON backup of clips."""
    count = bulk_import_clips(payload.clips)
    return {"status": "success", "imported_count": count}


# ============================================================================
# History, Radar & Backup
# ============================================================================

@app.get("/api/history", tags=["History"])
async def history_endpoint(
    limit: int = Query(default=20, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
):
    """Returns the latest saved sentence corrections and error classifications."""
    records = get_history(limit=limit, offset=offset)
    return {
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "items": records,
    }


@app.get("/api/radar", tags=["Radar"])
async def radar_endpoint():
    """Returns aggregated grammatical error statistics categorized for the error radar."""
    stats = get_radar_stats()
    return stats


@app.post("/api/backup/telegram", tags=["Backup"])
async def telegram_backup_endpoint():
    """Safely backs up SQLite database using SQLite Online Backup API and sends it to Telegram."""
    try:
        backup_result = await send_backup_to_telegram()
        return backup_result
    except TelegramConfigMissingError as tcme:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(tcme),
        )
    except TelegramBackupError as tbe:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(tbe),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected backup error: {str(e)}",
        )
