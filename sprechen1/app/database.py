import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from app.config import settings

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL UNIQUE,
                arabic_meaning TEXT DEFAULT '',
                label TEXT DEFAULT 'جملة',
                grammar_notes TEXT DEFAULT '',
                examples_json TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                user_sentence TEXT NOT NULL,
                is_correct INTEGER DEFAULT 0,
                corrected_german TEXT NOT NULL,
                arabic_meaning TEXT DEFAULT '',
                why_wrong TEXT DEFAULT '',
                replaced_words_json TEXT DEFAULT '[]',
                radar_rules_json TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Insert initial demo clips if empty
        cur = conn.execute("SELECT COUNT(*) as cnt FROM clips;")
        count = cur.fetchone()["cnt"]
        if count == 0:
            demo_clips = [
                (
                    "clip-init-1",
                    "Ich habe immer Angst, dass ich einschlafe, wenn ich vor meinem Computer sitze.",
                    "أخشى دائماً أن يغلبني النوم (أغفو) عندما أجلس أمام حاسوبي.",
                    "تصحيح سياقي B2",
                    "• (wenn) بدلاً من (als) لأن الحدث متكرر مع (immer).\n• (vor meinem Computer) حالة Dativ بدون (dem) مع الفعل (sitze) في آخر الجملة.\n• (einschlafe = أغفو) بدلاً من (verschlafe = تروح عليّ نومة صباحاً).",
                    json.dumps([
                        {"de": "Immer wenn ich abends lange vor meinem Computer sitze, werde ich müde.", "ar": "دائماً عندما أجلس طويلاً أمام حاسوبي مساءً، أشعر بالتعب."},
                        {"de": "Heute Morgen habe ich leider verschlafen und den Bus verpasst.", "ar": "هذا الصباح للأسف راحت عليّ نومة وفاتني الباص."}
                    ], ensure_ascii=False)
                ),
                (
                    "clip-init-2",
                    "zufriedenstellend",
                    "مُرضٍ / مُقنع (لوصف النتائج والأشياء)",
                    "كلمة B2",
                    "• تُستخدم (zufriedenstellend) لوصف النتائج أو العمل، بينما (zufrieden) للشخص الراضي.",
                    json.dumps([
                        {"de": "Die Ergebnisse waren leider nicht zufriedenstellend.", "ar": "النتائج لم تكن مُرضية للأسف."},
                        {"de": "Wir haben endlich eine zufriedenstellende Lösung gefunden.", "ar": "وجدنا أخيراً حلاً مُرضياً."}
                    ], ensure_ascii=False)
                )
            ]
            conn.executemany("""
                INSERT OR IGNORE INTO clips (id, text, arabic_meaning, label, grammar_notes, examples_json)
                VALUES (?, ?, ?, ?, ?, ?);
            """, demo_clips)
