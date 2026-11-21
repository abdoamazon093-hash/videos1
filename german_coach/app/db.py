import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import DB_PATH


def get_db_path() -> Path:
    """Returns the Path to the SQLite database, ensuring its parent directory exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    """Creates a connection to SQLite with row factory and foreign keys enabled."""
    db_file = get_db_path()
    conn = sqlite3.connect(str(db_file), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Initializes tables and indexes for German Coach if they do not exist."""
    conn = get_connection()
    try:
        with conn:
            # 1. Corrections History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_text TEXT NOT NULL,
                    corrected_text TEXT NOT NULL,
                    direct_correction TEXT DEFAULT '',
                    native_version TEXT DEFAULT '',
                    tone TEXT DEFAULT 'du',
                    direct_arabic_meaning TEXT DEFAULT '',
                    native_arabic_meaning TEXT DEFAULT '',
                    level TEXT NOT NULL,
                    explanation TEXT,
                    arabic_translations TEXT DEFAULT '[]',
                    diff_data TEXT DEFAULT '[]',
                    contextual_examples TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
            """)

            # 2. Grammar Error Logs (for Radar)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correction_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    error_text TEXT,
                    correction_text TEXT,
                    explanation TEXT,
                    arabic_trap INTEGER DEFAULT 0,
                    rule_tag TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (correction_id) REFERENCES corrections(id) ON DELETE CASCADE
                );
            """)

            # 3. Correction Cache (Sub-5ms instant response for identical sentences)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS correction_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_key TEXT UNIQUE NOT NULL,
                    level TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # 4. Word Meanings Cache (For Section 2 word click lookups)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS word_meanings_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_lower TEXT UNIQUE NOT NULL,
                    german_word TEXT NOT NULL,
                    arabic_meaning TEXT NOT NULL,
                    examples_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
            """)

            # 5. Conversation Turns (Section 3 persistent session)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_sentence TEXT NOT NULL,
                    corrected_german TEXT NOT NULL,
                    arabic_meaning TEXT,
                    is_correct INTEGER DEFAULT 0,
                    summary_ar TEXT,
                    created_at TEXT NOT NULL
                );
            """)

            # 6. Persistent Smart Clips (Section 6 Clipboard)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT UNIQUE COLLATE NOCASE NOT NULL,
                    arabic_meaning TEXT,
                    label TEXT,
                    grammar_explanation TEXT,
                    examples_json TEXT DEFAULT '[]',
                    synonyms_json TEXT DEFAULT '[]',
                    is_open INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 7. AI Assistant Chat History (Section 3 quick grammar assistant)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_chat (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer_ar TEXT NOT NULL,
                    german_highlight TEXT,
                    examples_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
            """)

            # Safe Automated Schema Migration for existing SQLite tables (run before index creation)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(error_logs);")
            existing_err_cols = {row["name"] for row in cursor.fetchall()}
            if "arabic_trap" not in existing_err_cols:
                conn.execute("ALTER TABLE error_logs ADD COLUMN arabic_trap INTEGER DEFAULT 0;")
            if "rule_tag" not in existing_err_cols:
                conn.execute("ALTER TABLE error_logs ADD COLUMN rule_tag TEXT DEFAULT '';")

            cursor.execute("PRAGMA table_info(corrections);")
            existing_corr_cols = {row["name"] for row in cursor.fetchall()}
            for col in ["direct_correction", "native_version", "tone", "direct_arabic_meaning", "native_arabic_meaning"]:
                if col not in existing_corr_cols:
                    conn.execute(f"ALTER TABLE corrections ADD COLUMN {col} TEXT DEFAULT '';")

            # Indexes for maximum query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_created ON corrections(created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_category ON error_logs(category);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_correction_id ON error_logs(correction_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_arabic_trap ON error_logs(arabic_trap);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_correction_cache_key ON correction_cache(normalized_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_word_meanings_word ON word_meanings_cache(word_lower);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_id ON turns(id ASC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_text ON clips(text COLLATE NOCASE);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_id ON ai_chat(id DESC);")
    finally:
        conn.close()


def check_db_health() -> bool:
    """Checks whether the database is accessible and working."""
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
        finally:
            conn.close()
    except Exception:
        return False


# ============================================================================
# Phase 1: Core Corrections & History
# ============================================================================

def save_correction(
    original_text: str,
    corrected_text: str,
    level: str,
    explanation: Optional[str] = None,
    arabic_translations: Optional[List[Dict[str, Any]]] = None,
    diff_data: Optional[List[Dict[str, Any]]] = None,
    contextual_examples: Optional[List[str]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    direct_correction: Optional[str] = None,
    native_version: Optional[str] = None,
    tone: Optional[str] = "du",
    direct_arabic_meaning: Optional[str] = None,
    native_arabic_meaning: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves a sentence correction and all its classified errors to SQLite."""
    arabic_translations = arabic_translations or []
    diff_data = diff_data or []
    contextual_examples = contextual_examples or []
    errors = errors or []
    direct_corr = direct_correction or corrected_text
    native_ver = native_version or corrected_text
    dir_ar = direct_arabic_meaning or ""
    nat_ar = native_arabic_meaning or ""
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO corrections (
                    original_text, corrected_text, direct_correction, native_version,
                    tone, direct_arabic_meaning, native_arabic_meaning, level, explanation,
                    arabic_translations, diff_data, contextual_examples, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    original_text,
                    corrected_text,
                    direct_corr,
                    native_ver,
                    tone or "du",
                    dir_ar,
                    nat_ar,
                    level.upper(),
                    explanation or "",
                    json.dumps(arabic_translations, ensure_ascii=False),
                    json.dumps(diff_data, ensure_ascii=False),
                    json.dumps(contextual_examples, ensure_ascii=False),
                    now_iso,
                ),
            )
            correction_id = cursor.lastrowid

            for err in errors:
                is_trap = 1 if err.get("arabic_trap") else 0
                r_tag = err.get("rule_tag", "")
                err_text = err.get("original") or err.get("error_text", "")
                corr_text = err.get("correction") or err.get("correction_text", "")
                expl = err.get("explanation_ar") or err.get("explanation", "")
                cat = err.get("category", "grammar")

                cursor.execute(
                    """
                    INSERT INTO error_logs (
                        correction_id, category, error_text, correction_text, explanation,
                        arabic_trap, rule_tag, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        correction_id,
                        cat,
                        err_text,
                        corr_text,
                        expl,
                        is_trap,
                        r_tag,
                        now_iso,
                    ),
                )

        return {
            "id": correction_id,
            "original_text": original_text,
            "corrected_text": corrected_text,
            "direct_correction": direct_corr,
            "native_version": native_ver,
            "tone": tone or "du",
            "direct_arabic_meaning": dir_ar,
            "native_arabic_meaning": nat_ar,
            "level": level.upper(),
            "explanation": explanation or "",
            "arabic_translations": arabic_translations,
            "diff_data": diff_data,
            "contextual_examples": contextual_examples,
            "errors": errors,
            "created_at": now_iso,
        }
    finally:
        conn.close()


def get_history(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetches the latest saved corrections with their categorized errors."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, original_text, corrected_text, direct_correction, native_version,
                   tone, direct_arabic_meaning, native_arabic_meaning, level, explanation,
                   arabic_translations, diff_data, contextual_examples, created_at
            FROM corrections
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        result = []

        for row in rows:
            cid = row["id"]
            cursor.execute(
                """
                SELECT id, category, error_text, correction_text, explanation,
                       arabic_trap, rule_tag, created_at
                FROM error_logs
                WHERE correction_id = ?
                ORDER BY id ASC
                """,
                (cid,),
            )
            error_rows = cursor.fetchall()
            errors = [
                {
                    "id": er["id"],
                    "category": er["category"],
                    "error_text": er["error_text"],
                    "correction_text": er["correction_text"],
                    "explanation": er["explanation"],
                    "arabic_trap": bool(er["arabic_trap"]) if "arabic_trap" in er.keys() else False,
                    "rule_tag": er["rule_tag"] if "rule_tag" in er.keys() else "",
                    "created_at": er["created_at"],
                }
                for er in error_rows
            ]

            result.append({
                "id": row["id"],
                "original_text": row["original_text"],
                "corrected_text": row["corrected_text"],
                "direct_correction": row["direct_correction"] if "direct_correction" in row.keys() and row["direct_correction"] else row["corrected_text"],
                "native_version": row["native_version"] if "native_version" in row.keys() and row["native_version"] else row["corrected_text"],
                "tone": row["tone"] if "tone" in row.keys() and row["tone"] else "du",
                "direct_arabic_meaning": row["direct_arabic_meaning"] if "direct_arabic_meaning" in row.keys() else "",
                "native_arabic_meaning": row["native_arabic_meaning"] if "native_arabic_meaning" in row.keys() else "",
                "level": row["level"],
                "explanation": row["explanation"],
                "arabic_translations": json.loads(row["arabic_translations"] or "[]"),
                "diff_data": json.loads(row["diff_data"] or "[]"),
                "contextual_examples": json.loads(row["contextual_examples"] or "[]"),
                "errors": errors,
                "created_at": row["created_at"],
            })
        return result
    finally:
        conn.close()


def get_radar_stats() -> Dict[str, Any]:
    """Computes aggregated grammatical error statistics for the radar chart."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM corrections")
        total_corrections = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM error_logs")
        total_errors = cursor.fetchone()[0]

        # Arabic traps count
        arabic_traps_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM error_logs WHERE arabic_trap = 1")
            arabic_traps_count = cursor.fetchone()[0]
        except Exception:
            arabic_traps_count = 0

        # Category Breakdown
        category_breakdown = {"grammar": 0, "logic_l1": 0, "style": 0}
        cursor.execute(
            """
            SELECT category, COUNT(*) as count
            FROM error_logs
            GROUP BY category
            ORDER BY count DESC
            """
        )
        cat_rows = cursor.fetchall()

        categories = []
        for r in cat_rows:
            cat_name = r["category"]
            cat_count = r["count"]
            pct = round((cat_count / total_errors * 100), 1) if total_errors > 0 else 0.0

            if cat_name in category_breakdown:
                category_breakdown[cat_name] = cat_count

            cursor.execute(
                """
                SELECT error_text, correction_text, explanation, rule_tag, arabic_trap
                FROM error_logs
                WHERE category = ?
                ORDER BY id DESC
                LIMIT 3
                """,
                (cat_name,),
            )
            examples = [
                {
                    "error_text": er["error_text"],
                    "correction_text": er["correction_text"],
                    "explanation": er["explanation"],
                    "rule_tag": er["rule_tag"] if "rule_tag" in er.keys() else "",
                    "arabic_trap": bool(er["arabic_trap"]) if "arabic_trap" in er.keys() else False,
                }
                for er in cursor.fetchall()
            ]

            categories.append({
                "category": cat_name,
                "count": cat_count,
                "percentage": pct,
                "recent_examples": examples,
            })

        # Top Rule Tags
        top_rule_tags = []
        try:
            cursor.execute(
                """
                SELECT rule_tag, category, COUNT(*) as cnt
                FROM error_logs
                WHERE rule_tag IS NOT NULL AND rule_tag != ''
                GROUP BY rule_tag
                ORDER BY cnt DESC
                LIMIT 8
                """
            )
            top_rule_tags = [
                {"rule_tag": r["rule_tag"], "category": r["category"], "count": r["cnt"]}
                for r in cursor.fetchall()
            ]
        except Exception:
            top_rule_tags = []

        cursor.execute(
            """
            SELECT level, COUNT(*) as count
            FROM corrections
            GROUP BY level
            """
        )
        level_counts = {r["level"]: r["count"] for r in cursor.fetchall()}

        return {
            "total_corrections": total_corrections,
            "total_errors": total_errors,
            "arabic_traps_count": arabic_traps_count,
            "category_breakdown": category_breakdown,
            "top_rule_tags": top_rule_tags,
            "categories": categories,
            "level_breakdown": level_counts,
        }
    finally:
        conn.close()


# ============================================================================
# Phase 4A: SQLite Caching (Correction Cache & Word Meanings Cache)
# ============================================================================

def normalize_cache_key(text: str, level: str, tone: str = "du") -> str:
    """Normalizes sentence, level, and tone into a canonical cache key."""
    clean = " ".join(text.strip().lower().split())
    return f"{level.upper()}:{tone.lower()}:{clean}"


def get_cached_correction(normalized_key: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached correction response if present."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT response_json FROM correction_cache WHERE normalized_key = ?",
            (normalized_key,),
        )
        row = cursor.fetchone()
        if row and row["response_json"]:
            try:
                return json.loads(row["response_json"])
            except json.JSONDecodeError:
                return None
        return None
    finally:
        conn.close()


def set_cached_correction(normalized_key: str, level: str, data: Dict[str, Any]) -> None:
    """Stores correction response in SQLite cache for fast sub-5ms lookups."""
    now_iso = datetime.now(timezone.utc).isoformat()
    json_str = json.dumps(data, ensure_ascii=False)
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO correction_cache (normalized_key, level, response_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(normalized_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (normalized_key, level.upper(), json_str, now_iso),
            )
    finally:
        conn.close()


def get_cached_word(word: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached German word meaning and examples."""
    clean = word.strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT word_lower, german_word, arabic_meaning, examples_json FROM word_meanings_cache WHERE word_lower = ?",
            (clean,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "word": row["word_lower"],
                "german_word": row["german_word"],
                "arabic_meaning": row["arabic_meaning"],
                "examples": json.loads(row["examples_json"] or "[]"),
            }
        return None
    finally:
        conn.close()


def set_cached_word(
    word: str,
    german_word: str,
    arabic_meaning: str,
    examples: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Stores word meaning in SQLite cache."""
    clean = word.strip().lower()
    examples = examples or []
    now_iso = datetime.now(timezone.utc).isoformat()
    json_str = json.dumps(examples, ensure_ascii=False)

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO word_meanings_cache (word_lower, german_word, arabic_meaning, examples_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(word_lower) DO UPDATE SET
                    german_word = excluded.german_word,
                    arabic_meaning = excluded.arabic_meaning,
                    examples_json = excluded.examples_json,
                    created_at = excluded.created_at
                """,
                (clean, german_word, arabic_meaning, json_str, now_iso),
            )
        return {
            "word": clean,
            "german_word": german_word,
            "arabic_meaning": arabic_meaning,
            "examples": examples,
        }
    finally:
        conn.close()


# ============================================================================
# Phase 4A: Turns (Section 3 Persistent Conversation)
# ============================================================================

def get_turns(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Retrieves conversation turns in chronological order."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_sentence, corrected_german, arabic_meaning, is_correct, summary_ar, created_at
            FROM turns
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "user_sentence": r["user_sentence"],
                "corrected_german": r["corrected_german"],
                "arabic_meaning": r["arabic_meaning"] or "",
                "is_correct": bool(r["is_correct"]),
                "summary_ar": r["summary_ar"] or "",
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def save_turn(
    user_sentence: str,
    corrected_german: str,
    arabic_meaning: Optional[str] = None,
    is_correct: bool = False,
    summary_ar: Optional[str] = None,
) -> Dict[str, Any]:
    """Saves a new conversation turn."""
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO turns (user_sentence, corrected_german, arabic_meaning, is_correct, summary_ar, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_sentence,
                    corrected_german,
                    arabic_meaning or "",
                    1 if is_correct else 0,
                    summary_ar or "",
                    now_iso,
                ),
            )
            turn_id = cursor.lastrowid
        return {
            "id": turn_id,
            "user_sentence": user_sentence,
            "corrected_german": corrected_german,
            "arabic_meaning": arabic_meaning or "",
            "is_correct": is_correct,
            "summary_ar": summary_ar or "",
            "created_at": now_iso,
        }
    finally:
        conn.close()


def delete_turn(turn_id: int) -> bool:
    """Deletes a conversation turn by id."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM turns WHERE id = ?", (turn_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def clear_turns() -> int:
    """Clears all conversation turns."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM turns")
            return cursor.rowcount
    finally:
        conn.close()


def bulk_insert_turns(turns_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inserts a list of turns (used for Undo/Restore)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    inserted = []
    try:
        with conn:
            for t in turns_list:
                user_sentence = t.get("user_sentence", "")
                corrected = t.get("corrected_german", "")
                arabic_meaning = t.get("arabic_meaning", "")
                is_correct = 1 if t.get("is_correct") else 0
                summary_ar = t.get("summary_ar", "")
                created_at = t.get("created_at") or now_iso

                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO turns (user_sentence, corrected_german, arabic_meaning, is_correct, summary_ar, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_sentence, corrected, arabic_meaning, is_correct, summary_ar, created_at),
                )
                inserted.append({
                    "id": cursor.lastrowid,
                    "user_sentence": user_sentence,
                    "corrected_german": corrected,
                    "arabic_meaning": arabic_meaning,
                    "is_correct": bool(is_correct),
                    "summary_ar": summary_ar,
                    "created_at": created_at,
                })
        return inserted
    finally:
        conn.close()


# ============================================================================
# Phase 4A: Smart Clips (Section 6 Persistent Clipboard)
# ============================================================================

def get_clips() -> List[Dict[str, Any]]:
    """Fetches all smart clips sorted by latest update."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, text, arabic_meaning, label, grammar_explanation,
                   examples_json, synonyms_json, is_open, created_at, updated_at
            FROM clips
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "arabic_meaning": r["arabic_meaning"] or "",
                "label": r["label"] or "",
                "grammar_explanation": r["grammar_explanation"] or "",
                "examples": json.loads(r["examples_json"] or "[]"),
                "synonyms": json.loads(r["synonyms_json"] or "[]"),
                "is_open": bool(r["is_open"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_clip_by_id(clip_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a single clip by id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, text, arabic_meaning, label, grammar_explanation,
                   examples_json, synonyms_json, is_open, created_at, updated_at
            FROM clips
            WHERE id = ?
            """,
            (clip_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "id": r["id"],
            "text": r["text"],
            "arabic_meaning": r["arabic_meaning"] or "",
            "label": r["label"] or "",
            "grammar_explanation": r["grammar_explanation"] or "",
            "examples": json.loads(r["examples_json"] or "[]"),
            "synonyms": json.loads(r["synonyms_json"] or "[]"),
            "is_open": bool(r["is_open"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    finally:
        conn.close()


def save_clip(
    text: str,
    arabic_meaning: Optional[str] = None,
    label: Optional[str] = None,
    grammar_explanation: Optional[str] = None,
    examples: Optional[List[Dict[str, str]]] = None,
    synonyms: Optional[List[str]] = None,
    is_open: bool = False,
) -> Dict[str, Any]:
    """Saves or updates a clip by its unique German text."""
    clean_text = text.strip()
    examples = examples or []
    synonyms = synonyms or []
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO clips (
                    text, arabic_meaning, label, grammar_explanation,
                    examples_json, synonyms_json, is_open, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(text COLLATE NOCASE) DO UPDATE SET
                    arabic_meaning = CASE WHEN excluded.arabic_meaning != '' THEN excluded.arabic_meaning ELSE clips.arabic_meaning END,
                    label = CASE WHEN excluded.label != '' THEN excluded.label ELSE clips.label END,
                    grammar_explanation = CASE WHEN excluded.grammar_explanation != '' THEN excluded.grammar_explanation ELSE clips.grammar_explanation END,
                    examples_json = CASE WHEN excluded.examples_json != '[]' THEN excluded.examples_json ELSE clips.examples_json END,
                    synonyms_json = CASE WHEN excluded.synonyms_json != '[]' THEN excluded.synonyms_json ELSE clips.synonyms_json END,
                    is_open = excluded.is_open,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_text,
                    arabic_meaning or "",
                    label or "",
                    grammar_explanation or "",
                    json.dumps(examples, ensure_ascii=False),
                    json.dumps(synonyms, ensure_ascii=False),
                    1 if is_open else 0,
                    now_iso,
                    now_iso,
                ),
            )
            # Fetch the upserted row
            cursor.execute("SELECT id FROM clips WHERE text = ? COLLATE NOCASE", (clean_text,))
            row = cursor.fetchone()
            clip_id = row["id"] if row else cursor.lastrowid

        return get_clip_by_id(clip_id) or {
            "id": clip_id,
            "text": clean_text,
            "arabic_meaning": arabic_meaning or "",
            "label": label or "",
            "grammar_explanation": grammar_explanation or "",
            "examples": examples,
            "synonyms": synonyms,
            "is_open": is_open,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    finally:
        conn.close()


def update_clip(clip_id: int, **fields) -> Optional[Dict[str, Any]]:
    """Updates fields of an existing clip."""
    existing = get_clip_by_id(clip_id)
    if not existing:
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    arabic_meaning = fields.get("arabic_meaning", existing["arabic_meaning"])
    label = fields.get("label", existing["label"])
    grammar_explanation = fields.get("grammar_explanation", existing["grammar_explanation"])
    examples = fields.get("examples", existing["examples"])
    synonyms = fields.get("synonyms", existing["synonyms"])
    is_open = 1 if fields.get("is_open", existing["is_open"]) else 0

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE clips SET
                    arabic_meaning = ?,
                    label = ?,
                    grammar_explanation = ?,
                    examples_json = ?,
                    synonyms_json = ?,
                    is_open = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    arabic_meaning,
                    label,
                    grammar_explanation,
                    json.dumps(examples, ensure_ascii=False),
                    json.dumps(synonyms, ensure_ascii=False),
                    is_open,
                    now_iso,
                    clip_id,
                ),
            )
        return get_clip_by_id(clip_id)
    finally:
        conn.close()


def delete_clip(clip_id: int) -> bool:
    """Deletes a clip by id."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def clear_clips() -> int:
    """Deletes all clips."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clips")
            return cursor.rowcount
    finally:
        conn.close()


def bulk_import_clips(clips_list: List[Dict[str, Any]]) -> int:
    """Imports or merges a list of clips from JSON backup."""
    imported_count = 0
    for c in clips_list:
        text = c.get("text", "").strip()
        if not text:
            continue
        save_clip(
            text=text,
            arabic_meaning=c.get("arabic_meaning"),
            label=c.get("label"),
            grammar_explanation=c.get("grammar_explanation"),
            examples=c.get("examples") or [],
            synonyms=c.get("synonyms") or [],
            is_open=bool(c.get("is_open", False)),
        )
        imported_count += 1
    return imported_count


# ============================================================================
# Phase 4A: AI Assistant Chat History (Section 3 quick assistant)
# ============================================================================

def get_ai_chat(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetches latest AI assistant chat messages."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, question, answer_ar, german_highlight, examples_json, created_at
            FROM ai_chat
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "question": r["question"],
                "answer_ar": r["answer_ar"],
                "german_highlight": r["german_highlight"] or "",
                "examples": json.loads(r["examples_json"] or "[]"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def save_ai_chat(
    question: str,
    answer_ar: str,
    german_highlight: Optional[str] = None,
    examples: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Saves a question-answer pair into AI chat history."""
    now_iso = datetime.now(timezone.utc).isoformat()
    examples = examples or []
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ai_chat (question, answer_ar, german_highlight, examples_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    question.strip(),
                    answer_ar.strip(),
                    (german_highlight or "").strip(),
                    json.dumps(examples, ensure_ascii=False),
                    now_iso,
                ),
            )
            chat_id = cursor.lastrowid
        return {
            "id": chat_id,
            "question": question.strip(),
            "answer_ar": answer_ar.strip(),
            "german_highlight": (german_highlight or "").strip(),
            "examples": examples,
            "created_at": now_iso,
        }
    finally:
        conn.close()


def clear_ai_chat() -> int:
    """Clears all AI chat history."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ai_chat")
            return cursor.rowcount
    finally:
        conn.close()
