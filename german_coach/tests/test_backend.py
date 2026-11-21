import os
import sys
import unittest
from pathlib import Path

# Ensure isolated DB path for testing before importing app modules
os.environ["DB_PATH"] = "/tmp/test_german_coach.db"

# Ensure app is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.config import get_env_status
from app.main import app
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
    compute_word_diff,
    correct_sentence,
)
from app.telegram_backup import (
    TelegramConfigMissingError,
    create_safe_sqlite_backup,
)


class TestGermanCoachBackend(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_db_health_and_init(self):
        self.assertTrue(check_db_health())

    def test_word_diff(self):
        orig = "Ich habe ein Buch gekauft."
        corr = "Ich hatte ein Buch gekauft."
        diff = compute_word_diff(orig, corr)
        self.assertTrue(any(d["type"] == "removed" and "habe" in d["text"] for d in diff))
        self.assertTrue(any(d["type"] == "added" and "hatte" in d["text"] for d in diff))

    def test_save_and_retrieve_correction(self):
        sample_errors = [
            {
                "category": "Kasus",
                "error_text": "dem Buch",
                "correction_text": "das Buch",
                "explanation": "Akkusativobjekt erforderlich.",
            },
            {
                "category": "Wortstellung",
                "error_text": "weil ich bin müde",
                "correction_text": "weil ich müde bin",
                "explanation": "Verb am Ende im Nebensatz.",
            },
        ]
        sample_arabic = [
            {"arabic": "الكتاب", "german": "das Buch", "context": "Objekt"}
        ]
        sample_examples = [
            "Ich lese das Buch jeden Tag.",
            "Er schenkt ihr ein interessantes Buch.",
        ]

        saved = save_correction(
            original_text="Ich kaufe dem الكتاب weil ich bin müde.",
            corrected_text="Ich kaufe das Buch, weil ich müde bin.",
            level="B2",
            explanation="Korrektur von Kasus und Wortstellung im Nebensatz.",
            arabic_translations=sample_arabic,
            diff_data=[{"type": "equal", "text": "Ich kaufe "}],
            contextual_examples=sample_examples,
            errors=sample_errors,
        )

        self.assertIsNotNone(saved["id"])
        self.assertEqual(saved["level"], "B2")

        # Test history
        history = get_history(limit=5)
        self.assertGreaterEqual(len(history), 1)
        latest = history[0]
        self.assertEqual(latest["id"], saved["id"])
        self.assertEqual(len(latest["errors"]), 2)
        self.assertEqual(latest["arabic_translations"][0]["arabic"], "الكتاب")

        # Test radar
        radar = get_radar_stats()
        self.assertGreaterEqual(radar["total_corrections"], 1)
        self.assertGreaterEqual(radar["total_errors"], 2)
        categories = {c["category"]: c["count"] for c in radar["categories"]}
        self.assertIn("Kasus", categories)
        self.assertIn("Wortstellung", categories)

    def test_safe_backup_creation(self):
        backup_file = create_safe_sqlite_backup()
        self.assertTrue(backup_file.exists())
        self.assertTrue(backup_file.name.endswith(".db.gz"))
        self.assertGreater(backup_file.stat().st_size, 0)
        # Clean up backup test file
        backup_file.unlink()

    def test_frontend_index_and_static(self):
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("German Coach", response.text)

        # Check static files
        js_resp = client.get("/static/app.js")
        self.assertEqual(js_resp.status_code, 200)

        css_resp = client.get("/static/styles.css")
        self.assertEqual(css_resp.status_code, 200)

    def test_correction_caching(self):
        key = normalize_cache_key("Ich habe ein Buch gekauft.", "B2")
        self.assertEqual(key, "B2:du:ich habe ein buch gekauft.")

        sample_data = {
            "corrected_text": "Ich habe ein Buch gekauft.",
            "arabic_meaning": "اشتريت كتاباً.",
            "is_correct": True,
            "summary_ar": "الجملة صحيحة تماماً.",
        }
        set_cached_correction(key, "B2", sample_data)

        cached = get_cached_correction(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["corrected_text"], sample_data["corrected_text"])
        self.assertTrue(cached["is_correct"])

    def test_word_meanings_cache(self):
        word = "zufriedenstellend"
        sample_examples = [{"de": "Das ist zufriedenstellend.", "ar": "هذا مرضٍ."}]
        saved = set_cached_word(word, "zufriedenstellend", "مرضٍ / مقبول", sample_examples)
        self.assertEqual(saved["word"], word)

        retrieved = get_cached_word("ZUFRIEDENSTELLEND")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["arabic_meaning"], "مرضٍ / مقبول")
        self.assertEqual(len(retrieved["examples"]), 1)

    def test_turns_crud_and_bulk(self):
        clear_turns()
        turn1 = save_turn(
            user_sentence="Ich gehe Schule.",
            corrected_german="Ich gehe zur Schule.",
            arabic_meaning="أنا ذاهب إلى المدرسة.",
            is_correct=False,
            summary_ar="إضافة حرف الجر zur.",
        )
        self.assertIsNotNone(turn1["id"])

        turns = get_turns()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["corrected_german"], "Ich gehe zur Schule.")

        # Test single delete
        deleted = delete_turn(turn1["id"])
        self.assertTrue(deleted)
        self.assertEqual(len(get_turns()), 0)

        # Test bulk insert (Undo)
        bulk_data = [
            {"user_sentence": "Satz 1", "corrected_german": "Satz 1", "is_correct": True},
            {"user_sentence": "Satz 2", "corrected_german": "Satz 2", "is_correct": False},
        ]
        inserted = bulk_insert_turns(bulk_data)
        self.assertEqual(len(inserted), 2)
        self.assertEqual(len(get_turns()), 2)
        clear_turns()

    def test_clips_crud_and_import(self):
        clear_clips()
        clip = save_clip(
            text="aus diesem Grund",
            arabic_meaning="لهذا السبب",
            label="Redemittel",
            grammar_explanation="Inversion nach Konnektor",
            examples=[{"de": "Aus diesem Grund lerne ich.", "ar": "لهذا السبب أتعلم."}],
            synonyms=["deshalb", "daher"],
            is_open=True,
        )
        self.assertIsNotNone(clip["id"])
        self.assertEqual(clip["text"], "aus diesem Grund")

        # Test upsert by text case-insensitively
        clip_updated = save_clip(
            text="AUS DIESEM GRUND",
            label="B2 Redemittel",
        )
        self.assertEqual(clip_updated["id"], clip["id"])
        self.assertEqual(clip_updated["label"], "B2 Redemittel")

        # Test update
        updated = update_clip(clip["id"], arabic_meaning="لهذا السبب تحديداً")
        self.assertEqual(updated["arabic_meaning"], "لهذا السبب تحديداً")

        # Test bulk import
        imported = bulk_import_clips([
            {"text": "meiner Meinung nach", "arabic_meaning": "في رأيي"},
            {"text": "im Vergleich zu", "arabic_meaning": "مقارنة بـ"},
        ])
        self.assertEqual(imported, 2)
        all_clips = get_clips()
        self.assertEqual(len(all_clips), 3)

        # Clean
        delete_clip(clip["id"])
        clear_clips()
        self.assertEqual(len(get_clips()), 0)

    def test_ai_chat_crud(self):
        clear_ai_chat()
        chat = save_ai_chat(
            question="ما الفرق بين weil و denn؟",
            answer_ar="weil يرسل الفعل للمؤخرة، بينما denn لا يغير ترتيب الجملة.",
            german_highlight="weil (Nebensatz) vs denn (Hauptsatz)",
            examples=["Ich lerne, weil ich will.", "Ich lerne, denn ich will."],
        )
        self.assertIsNotNone(chat["id"])
        history = get_ai_chat()
        self.assertEqual(len(history), 1)
        self.assertIn("weil", history[0]["answer_ar"])
        clear_ai_chat()
        self.assertEqual(len(get_ai_chat()), 0)

    def test_api_endpoints_via_testclient(self):
        client = TestClient(app)

        # 1. Word endpoint (with cache pre-population)
        set_cached_word("aufmerksam", "aufmerksam", "منتبه / حريص", [{"de": "Sei aufmerksam!", "ar": "كن منتبهاً!"}])
        resp_word = client.post("/api/word", json={"word": "aufmerksam"})
        self.assertEqual(resp_word.status_code, 200)
        self.assertTrue(resp_word.json()["cached"])
        self.assertEqual(resp_word.json()["arabic_meaning"], "منتبه / حريص")

        # 2. Turns endpoints
        resp_turn = client.post("/api/turns", json={
            "user_sentence": "Hallo wie gehts",
            "corrected_german": "Hallo, wie geht's?",
            "is_correct": False,
        })
        self.assertEqual(resp_turn.status_code, 200)
        turn_id = resp_turn.json()["id"]

        resp_turns = client.get("/api/turns")
        self.assertEqual(resp_turns.status_code, 200)
        self.assertGreaterEqual(resp_turns.json()["total"], 1)

        resp_del_turn = client.delete(f"/api/turns/{turn_id}")
        self.assertEqual(resp_del_turn.status_code, 200)

        # 3. Clips endpoints
        resp_clip = client.post("/api/clips", json={
            "text": "Es kommt darauf an",
            "arabic_meaning": "هذا يعتمد",
        })
        self.assertEqual(resp_clip.status_code, 200)
        clip_id = resp_clip.json()["id"]

        resp_clips = client.get("/api/clips")
        self.assertEqual(resp_clips.status_code, 200)
        self.assertGreaterEqual(resp_clips.json()["total"], 1)

        resp_del_clip = client.delete(f"/api/clips/{clip_id}")
        self.assertEqual(resp_del_clip.status_code, 200)

        # 3b. Test creating clip without arabic_meaning (auto-translation from word cache)
        set_cached_word("Buch", "das Buch", "كتاب", [{"de": "Ich lese ein Buch.", "ar": "أنا أقرأ كتاباً."}])
        resp_auto_clip = client.post("/api/clips", json={"text": "Buch"})
        self.assertEqual(resp_auto_clip.status_code, 200)
        self.assertEqual(resp_auto_clip.json()["arabic_meaning"], "كتاب")
        client.delete(f"/api/clips/{resp_auto_clip.json()['id']}")

        # 4. Correction endpoint Cache hit
        cache_key = normalize_cache_key("Ich trinke Kaffee.", "B2")
        set_cached_correction(cache_key, "B2", {
            "corrected_text": "Ich trinke Kaffee.",
            "arabic_meaning": "أنا أشرب القهوة.",
            "is_correct": True,
            "summary_ar": "صحيحة.",
        })
        resp_corr = client.post("/api/correct", json={"text": "Ich trinke Kaffee.", "level": "B2"})
        self.assertEqual(resp_corr.status_code, 200)
        self.assertTrue(resp_corr.json()["cached"])
        self.assertLess(resp_corr.json()["elapsed_ms"], 50.0)

    def test_reference_sentence_correction_engine(self):
        """
        Tests the 4-layer correction engine on the reference sentence:
        Verifies logic_l1 (Arabic traps), grammar, silent ASR cleanup,
        conjunction preservation, and non-repetition in native_version.
        """
        ref_text = (
            "hallo und Bruder ich möchte mal mit dir sprechen bist du bereit für ein nettes Gespräch "
            "wir haben gestern vereinbart dass wir gerade ein nettes Gespräch führen wie gestern "
            "was hältst du davon wenn wir aber etwas anders machen weil ich gerade auf meinem Laptop Sitze okay sag mal wenn"
        )
        result = correct_sentence(ref_text, level="B2", tone="du")
        self.assertIn("direct_correction", result)
        self.assertIn("native_version", result)
        self.assertIn("errors", result)

        errors = result["errors"]

        # 1. auf meinem Laptop identified as logic_l1 with arabic_trap: true
        laptop_err = next((e for e in errors if "laptop" in e.get("original", "").lower()), None)
        self.assertIsNotNone(laptop_err, "auf meinem Laptop must be identified as an error")
        self.assertEqual(laptop_err.get("category"), "logic_l1")
        self.assertTrue(laptop_err.get("arabic_trap"))
        self.assertTrue(
            "am laptop" in laptop_err.get("correction", "").lower()
            or "vor meinem laptop" in laptop_err.get("correction", "").lower()
        )

        # 2. etwas anders -> etwas anderes (grammar)
        anders_err = next((e for e in errors if "anders" in e.get("original", "").lower()), None)
        self.assertIsNotNone(anders_err, "etwas anders must be identified as an error")
        self.assertEqual(anders_err.get("category"), "grammar")
        self.assertIn("anderes", anders_err.get("correction", "").lower())

        # 3. wenn -> wann (grammar)
        wenn_err = next((e for e in errors if "wenn" in e.get("original", "").lower()), None)
        self.assertIsNotNone(wenn_err, "wenn/sag mal wenn must be identified as an error")
        self.assertEqual(wenn_err.get("category"), "grammar")
        self.assertIn("wann", wenn_err.get("correction", "").lower())

        # 4. Silent ASR cleanup: Sitze casing and punctuation are not counted in errors
        sitze_as_grammar = [
            e for e in errors
            if e.get("original", "").strip() == "Sitze" and e.get("category") == "grammar"
        ]
        self.assertEqual(len(sitze_as_grammar), 0, "Casing of Sitze should not be counted as a grammar error")

        # 5. Connector 'weil' preserved
        self.assertIn("weil", result["direct_correction"].lower())

        # 6. native_version does not repeat 'ein nettes Gespräch'
        native = result["native_version"].lower()
        self.assertLessEqual(native.count("nettes gespräch"), 1)

    def test_radar_and_history_endpoints_with_migration(self):
        """Verifies /api/radar and /api/history return intact data including arabic_traps."""
        client = TestClient(app)
        res_radar = client.get("/api/radar")
        self.assertEqual(res_radar.status_code, 200)
        data = res_radar.json()
        self.assertIn("arabic_traps_count", data)
        self.assertIn("categories", data)
        self.assertIn("total_corrections", data)

        res_hist = client.get("/api/history")
        self.assertEqual(res_hist.status_code, 200)
        hist_data = res_hist.json()
        self.assertIn("items", hist_data)


if __name__ == "__main__":
    unittest.main()
