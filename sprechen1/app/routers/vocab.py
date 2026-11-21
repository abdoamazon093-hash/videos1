import re
import json
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.db import get_db
from app.services.case_classifier import classify_case

router = APIRouter(prefix="/api", tags=["vocabulary"])
logger = logging.getLogger(__name__)


class CustomExampleRequest(BaseModel):
    de: str
    ar: Optional[str] = ""


class BulkProgressSync(BaseModel):
    learned_ids: List[int] = []
    review_ids: List[int] = []


def german_sort_key(text: str):
    """
    Standard German DIN 5007-1 alphabetical sort key.
    Handles German umlauts (ä->a, ö->o, ü->u, ß->ss), strips articles & reflexive 'sich'.
    """
    t = (text or "").lower().strip()
    for art in ["der ", "die ", "das "]:
        if t.startswith(art):
            t = t[len(art):].strip()
            break
    if t.startswith("sich "):
        t = t[5:].strip() + " sich"
    elif ", sich" in t:
        t = t.replace(", sich", "").strip() + " sich"
    t = t.lstrip("#")
    t_clean = re.sub(r"[/()\-\–,\.]", "", t).strip()
    norm = (
        t_clean.replace("ä", "a")
               .replace("ö", "o")
               .replace("ü", "u")
               .replace("ß", "ss")
    )
    return (norm, t_clean)


@router.get("/documents/{document_id}/words")
def get_document_words(
    document_id: int,
    page: Optional[str] = Query("all"),
    status: Optional[str] = Query("all"),
    sort: Optional[str] = Query("alpha"),
    q: Optional[str] = Query("")
):
    """
    Returns vocabulary words for a given document with filtering & sorting:
    - sort: 'alpha' (A-Z starting from 1, default), 'alpha_desc' (Z-A), 'original' (document order)
    - page: 'all' or specific page number
    - status: 'all', 'verbs', 'learned', 'review', 'unlearned'
    - q: search query across word, spoken_word, arabic, synonym, perfekt, or word number
    """
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        sql = """
            SELECT w.*, 
                   COALESCE(p.is_learned, 0) as is_learned,
                   COALESCE(p.is_review, 0) as is_review,
                   p.custom_example_de,
                   p.custom_example_ar
            FROM vocabulary_words w
            LEFT JOIN user_progress p ON w.id = p.word_id
            WHERE w.document_id = ?
            ORDER BY w.page_number ASC, w.id ASC
        """
        words_rows = conn.execute(sql, (document_id,)).fetchall()

        if not words_rows:
            return {"document": dict(doc), "words": [], "total_count": 0}

        word_ids = [r["id"] for r in words_rows]
        placeholders = ",".join("?" for _ in word_ids)
        ex_rows = conn.execute(f"""
            SELECT word_id, tag, de_sentence, ar_sentence
            FROM word_examples
            WHERE word_id IN ({placeholders})
            ORDER BY word_id, order_index
        """, word_ids).fetchall()

        ex_map = {}
        for e in ex_rows:
            wid = e["word_id"]
            if wid not in ex_map:
                ex_map[wid] = []
            ex_map[wid].append({
                "tag": e["tag"],
                "de": e["de_sentence"],
                "ar": e["ar_sentence"]
            })

        all_items = []
        for r in words_rows:
            wid = r["id"]
            syn_list = json.loads(r["synonym_list_json"] or "[]")
            is_v = bool(r["is_verb"])
            c_case = r["grammatical_case"] if ("grammatical_case" in r.keys() and r["grammatical_case"] and r["grammatical_case"] != "none") else classify_case(r["synonym"], r["word"], is_v)
            all_items.append({
                "id": wid,
                "document_id": r["document_id"],
                "page": r["page_number"],
                "word": r["word"],
                "spokenWord": r["spoken_word"],
                "youglishQuery": r["youglish_query"],
                "arabic": r["arabic"],
                "synonym": r["synonym"],
                "synonymList": syn_list,
                "grammatical_case": c_case,
                "is_verb": bool(r["is_verb"]),
                "perfekt": r["perfekt"] or "",
                "praeteritum": r["praeteritum"] or "" if "praeteritum" in r.keys() else "",
                "is_learned": bool(r["is_learned"]),
                "is_review": bool(r["is_review"]),
                "custom_example_de": r["custom_example_de"],
                "custom_example_ar": r["custom_example_ar"],
                "examples": ex_map.get(wid, [])
            })

        # Apply sorting and numbering
        if sort == "akk_only":
            all_items = [it for it in all_items if it["grammatical_case"] == "akk"]
            all_items.sort(key=lambda x: german_sort_key(x["word"]))
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx
        elif sort == "dat_only":
            all_items = [it for it in all_items if it["grammatical_case"] == "dat"]
            all_items.sort(key=lambda x: german_sort_key(x["word"]))
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx
        elif sort == "both_only":
            all_items = [it for it in all_items if it["grammatical_case"] == "both"]
            all_items.sort(key=lambda x: german_sort_key(x["word"]))
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx
        elif sort == "akk_then_dat":
            case_rank = {"akk": 0, "both": 1, "dat": 2, "none": 3}
            all_items.sort(key=lambda x: (case_rank.get(x["grammatical_case"], 3), german_sort_key(x["word"])))
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx
        elif sort == "original":
            all_items.sort(key=lambda x: (x["page"], x["id"]))
            p_counters = {}
            for it in all_items:
                p = it["page"]
                p_counters[p] = p_counters.get(p, 0) + 1
                it["page_word_num"] = p_counters[p]
                it["alpha_num"] = p_counters[p]
        elif sort == "alpha_desc":
            all_items.sort(key=lambda x: german_sort_key(x["word"]), reverse=True)
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx
        else: # default: "alpha"
            all_items.sort(key=lambda x: german_sort_key(x["word"]))
            for idx, it in enumerate(all_items, 1):
                it["page_word_num"] = idx
                it["alpha_num"] = idx

        # If a single page is requested:
        if page != "all" and page.isdigit():
            target_p = int(page)
            filtered_items = [it for it in all_items if it["page"] == target_p]
            if sort == "original":
                for idx, it in enumerate(filtered_items, 1):
                    it["page_word_num"] = idx
        else:
            filtered_items = all_items

        if status == "verbs":
            filtered_items = [it for it in filtered_items if it["is_verb"] or it["perfekt"]]
        elif status == "learned":
            filtered_items = [it for it in filtered_items if it["is_learned"]]
        elif status == "review":
            filtered_items = [it for it in filtered_items if it["is_review"]]
        elif status == "unlearned":
            filtered_items = [it for it in filtered_items if not it["is_learned"]]
        elif status == "akk":
            filtered_items = [it for it in filtered_items if it["grammatical_case"] in ("akk", "both")]
        elif status == "dat":
            filtered_items = [it for it in filtered_items if it["grammatical_case"] in ("dat", "both")]
        elif status == "both":
            filtered_items = [it for it in filtered_items if it["grammatical_case"] == "both"]

        if q and q.strip():
            q_clean = q.strip().lower().replace("#", "")
            filtered_items = [
                it for it in filtered_items
                if q_clean in it["word"].lower()
                or q_clean in it["spokenWord"].lower()
                or q_clean in it["arabic"].lower()
                or q_clean in it["synonym"].lower()
                or q_clean in it["perfekt"].lower()
                or str(it["page_word_num"]) == q_clean
                or str(it["id"]) == q_clean
            ]

        return {
            "document": dict(doc),
            "words": filtered_items,
            "total_count": len(filtered_items)
        }


@router.post("/words/{word_id}/learned")
def toggle_learned(word_id: int, state: Optional[bool] = Query(None)):
    with get_db() as conn:
        prog = conn.execute("SELECT * FROM user_progress WHERE word_id = ?", (word_id,)).fetchone()
        if state is not None:
            new_val = 1 if state else 0
        elif prog:
            new_val = 0 if prog["is_learned"] else 1
        else:
            new_val = 1

        if prog:
            conn.execute("UPDATE user_progress SET is_learned = ?, updated_at = CURRENT_TIMESTAMP WHERE word_id = ?", (new_val, word_id))
        else:
            conn.execute("INSERT INTO user_progress (word_id, is_learned, is_review) VALUES (?, ?, 0)", (word_id, new_val))
        return {"word_id": word_id, "is_learned": bool(new_val)}


@router.post("/words/{word_id}/review")
def toggle_review(word_id: int, state: Optional[bool] = Query(None)):
    with get_db() as conn:
        prog = conn.execute("SELECT * FROM user_progress WHERE word_id = ?", (word_id,)).fetchone()
        if state is not None:
            new_val = 1 if state else 0
        elif prog:
            new_val = 0 if prog["is_review"] else 1
        else:
            new_val = 1

        if prog:
            conn.execute("UPDATE user_progress SET is_review = ?, updated_at = CURRENT_TIMESTAMP WHERE word_id = ?", (new_val, word_id))
        else:
            conn.execute("INSERT INTO user_progress (word_id, is_learned, is_review) VALUES (?, 0, ?)", (word_id, new_val))
        return {"word_id": word_id, "is_review": bool(new_val)}


@router.post("/words/{word_id}/custom-example")
def set_custom_example(word_id: int, payload: CustomExampleRequest):
    with get_db() as conn:
        prog = conn.execute("SELECT * FROM user_progress WHERE word_id = ?", (word_id,)).fetchone()
        if prog:
            conn.execute("""
                UPDATE user_progress
                SET custom_example_de = ?, custom_example_ar = ?, updated_at = CURRENT_TIMESTAMP
                WHERE word_id = ?
            """, (payload.de.strip(), (payload.ar or "").strip(), word_id))
        else:
            conn.execute("""
                INSERT INTO user_progress (word_id, is_learned, is_review, custom_example_de, custom_example_ar)
                VALUES (?, 0, 0, ?, ?)
            """, (word_id, payload.de.strip(), (payload.ar or "").strip()))
        return {"status": "success", "word_id": word_id, "custom_example_de": payload.de, "custom_example_ar": payload.ar}


@router.post("/documents/{document_id}/reset-progress")
def reset_progress(document_id: int):
    with get_db() as conn:
        conn.execute("""
            DELETE FROM user_progress 
            WHERE word_id IN (SELECT id FROM vocabulary_words WHERE document_id = ?)
        """, (document_id,))
        return {"status": "success", "message": f"Progress reset for document {document_id}"}


@router.post("/documents/{document_id}/clear-review")
def clear_document_review(document_id: int):
    """Clears all review marks for words in the specified document."""
    with get_db() as conn:
        conn.execute("""
            UPDATE user_progress 
            SET is_review = 0, updated_at = CURRENT_TIMESTAMP
            WHERE word_id IN (SELECT id FROM vocabulary_words WHERE document_id = ?)
        """, (document_id,))
        return {"status": "success", "message": f"Review list cleared for document {document_id}"}


@router.post("/documents/{document_id}/sync-progress")
def sync_document_progress(document_id: int, payload: BulkProgressSync):
    """Synchronizes client-side localStorage progress into SQLite."""
    with get_db() as conn:
        doc_words = set(r["id"] for r in conn.execute("SELECT id FROM vocabulary_words WHERE document_id = ?", (document_id,)).fetchall())
        for wid in payload.learned_ids:
            if wid in doc_words:
                conn.execute("""
                    INSERT INTO user_progress (word_id, is_learned, is_review)
                    VALUES (?, 1, 0)
                    ON CONFLICT(word_id) DO UPDATE SET is_learned = 1, updated_at = CURRENT_TIMESTAMP
                """, (wid,))
        for wid in payload.review_ids:
            if wid in doc_words:
                conn.execute("""
                    INSERT INTO user_progress (word_id, is_learned, is_review)
                    VALUES (?, 0, 1)
                    ON CONFLICT(word_id) DO UPDATE SET is_review = 1, updated_at = CURRENT_TIMESTAMP
                """, (wid,))
        return {"status": "success", "synced_learned": len(payload.learned_ids), "synced_review": len(payload.review_ids)}


@router.post("/documents/{document_id}/mark-all-learned")
def mark_all_learned(document_id: int):
    with get_db() as conn:
        words = conn.execute("SELECT id FROM vocabulary_words WHERE document_id = ?", (document_id,)).fetchall()
        for w in words:
            conn.execute("""
                INSERT INTO user_progress (word_id, is_learned, is_review)
                VALUES (?, 1, 0)
                ON CONFLICT(word_id) DO UPDATE SET is_learned = 1, updated_at = CURRENT_TIMESTAMP
            """, (w["id"],))
        return {"status": "success", "marked_count": len(words)}
