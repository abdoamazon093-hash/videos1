import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from app.config import DB_PATH

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction rolled back due to error: {e}")
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initializes tables and indexes with foreign keys and WAL mode."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            total_words INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vocabulary_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page_number INTEGER DEFAULT 1,
            word TEXT NOT NULL,
            spoken_word TEXT NOT NULL,
            youglish_query TEXT NOT NULL,
            arabic TEXT NOT NULL,
            synonym TEXT DEFAULT '',
            synonym_list_json TEXT DEFAULT '[]',
            is_verb BOOLEAN DEFAULT 0,
            perfekt TEXT DEFAULT '',
            praeteritum TEXT DEFAULT '',
            grammatical_case TEXT DEFAULT 'none',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS word_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER NOT NULL REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            de_sentence TEXT NOT NULL,
            ar_sentence TEXT NOT NULL,
            order_index INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_progress (
            word_id INTEGER PRIMARY KEY REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            is_learned BOOLEAN DEFAULT 0,
            is_review BOOLEAN DEFAULT 0,
            custom_example_de TEXT DEFAULT NULL,
            custom_example_ar TEXT DEFAULT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes for high-speed queries and filtering
        CREATE INDEX IF NOT EXISTS idx_vocab_doc_page ON vocabulary_words(document_id, page_number);
        CREATE INDEX IF NOT EXISTS idx_vocab_word ON vocabulary_words(word);
        CREATE INDEX IF NOT EXISTS idx_vocab_is_verb ON vocabulary_words(is_verb);
        CREATE INDEX IF NOT EXISTS idx_progress_status ON user_progress(is_learned, is_review);
        CREATE INDEX IF NOT EXISTS idx_examples_word ON word_examples(word_id);
        """)

        # Migration: ensure praeteritum column exists in vocabulary_words
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(vocabulary_words)").fetchall()]
        if "praeteritum" not in cols:
            conn.execute("ALTER TABLE vocabulary_words ADD COLUMN praeteritum TEXT DEFAULT ''")

        # Migration: ensure grammatical_case column exists in vocabulary_words
        if "grammatical_case" not in cols:
            conn.execute("ALTER TABLE vocabulary_words ADD COLUMN grammatical_case TEXT DEFAULT 'none'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vocab_case ON vocabulary_words(grammatical_case)")

        # Backfill grammatical_case for any existing vocabulary rows
        backfill_grammatical_cases(conn)

        logger.info("Database schema initialized successfully.")


def backfill_grammatical_cases(conn: sqlite3.Connection) -> None:
    """Classifies and populates grammatical_case for all existing vocabulary items."""
    try:
        from app.services.case_classifier import classify_case
        rows = conn.execute("SELECT id, synonym, word, is_verb, grammatical_case FROM vocabulary_words").fetchall()
        updates = []
        for r in rows:
            curr_case = r["grammatical_case"] if "grammatical_case" in r.keys() else None
            # Reclassify if missing or none
            if not curr_case or curr_case == "none":
                new_c = classify_case(r["synonym"], r["word"], bool(r["is_verb"]))
                if new_c != "none":
                    updates.append((new_c, r["id"]))
        if updates:
            conn.executemany("UPDATE vocabulary_words SET grammatical_case = ? WHERE id = ?", updates)
            logger.info(f"Backfilled grammatical_case for {len(updates)} vocabulary items.")
    except Exception as e:
        logger.warning(f"Could not backfill grammatical_case: {e}")



if __name__ == "__main__":
    init_db()
    print("DB initialized successfully.")
