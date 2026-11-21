import io
import json
import logging
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.config import UPLOADS_DIR
from app.db import get_db
from app.services.extractor import extract_vocabulary_from_file
from app.services.gemini_enricher import enrich_vocabulary_batch
from app.services.case_classifier import classify_case

router = APIRouter(prefix="/api/upload", tags=["upload"])
logger = logging.getLogger(__name__)


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(None)
):
    """
    Uploads a PDF or Word document, extracts vocabulary, enriches with Perfekt,
    synonyms, and B2 examples, and stores it in the database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename
    ext = Path(filename).suffix.lower()
    if ext not in [".docx", ".pdf", ".txt", ".tsv", ".csv"]:
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Only .docx, .pdf, and .txt files are supported."
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Save to uploads dir
    safe_name = f"{Path(filename).stem}_{Path(filename).suffix}"
    dest_path = UPLOADS_DIR / safe_name
    dest_path.write_bytes(file_bytes)

    # 1. Extract raw items
    try:
        raw_items = extract_vocabulary_from_file(file_bytes, filename)
    except Exception as e:
        logger.error(f"Error parsing file {filename}: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to extract words from document: {str(e)}")

    if not raw_items:
        raise HTTPException(status_code=400, detail="No vocabulary words could be found in the uploaded file.")

    doc_title = title.strip() if title and title.strip() else Path(filename).stem.replace("_", " ").title()

    # 2. Enrich in parallel batches of 20
    batch_size = 20
    chunks = [raw_items[i:i + batch_size] for i in range(0, len(raw_items), batch_size)]
    semaphore = asyncio.Semaphore(3)

    async def process_chunk(chunk):
        async with semaphore:
            return await enrich_vocabulary_batch(chunk)

    chunk_results = await asyncio.gather(*[process_chunk(c) for c in chunks])
    enriched_items = [item for sublist in chunk_results for item in sublist]

    # 3. Save into SQLite
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO documents (title, filename, file_type, total_words) VALUES (?, ?, ?, ?)",
            (doc_title, filename, ext.replace(".", ""), len(enriched_items))
        )
        doc_id = cursor.lastrowid

        for it in enriched_items:
            is_v = bool(it.get("is_verb", False))
            c_case = it.get("grammatical_case") or classify_case(it.get("synonym", ""), it.get("word", ""), is_v)
            w_cur = conn.execute("""
                INSERT INTO vocabulary_words 
                (document_id, page_number, word, spoken_word, youglish_query, arabic, synonym, synonym_list_json, is_verb, perfekt, praeteritum, grammatical_case)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                it.get("page", 1),
                it.get("word", ""),
                it.get("spoken_word", ""),
                it.get("youglish_query", ""),
                it.get("arabic", ""),
                it.get("synonym", ""),
                json.dumps(it.get("synonym_list", []), ensure_ascii=False),
                is_v,
                it.get("perfekt", ""),
                it.get("praeteritum", ""),
                c_case
            ))
            word_db_id = w_cur.lastrowid

            for idx, ex in enumerate(it.get("examples", [])):
                conn.execute("""
                    INSERT INTO word_examples (word_id, tag, de_sentence, ar_sentence, order_index)
                    VALUES (?, ?, ?, ?, ?)
                """, (word_db_id, ex.get("tag", "مثال"), ex.get("de", ""), ex.get("ar", ""), idx))

    return {
        "status": "success",
        "document_id": doc_id,
        "title": doc_title,
        "total_words": len(enriched_items),
        "message": f"Successfully extracted and enriched {len(enriched_items)} words."
    }


@router.get("/template/docx")
def download_docx_template():
    """Generates and serves a formatted Word (.docx) template with sample vocabulary columns."""
    doc = docx.Document()

    p = doc.add_paragraph()
    r = p.add_run("قالب مفردات وقوائم اللغة الألمانية — Vocab Tutor")
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = RGBColor(2, 132, 199)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub_r = sub.add_run("يمكنك ملء هذا الجدول بكلماتك مباشرة. يتعرف النظام تلقائياً على الأعمدة وترتيبها.")
    sub_r.font.size = Pt(11)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    headers = [
        "#", 
        "Infinitiv (المصدر) / الكلمة", 
        "Präteritum (الماضي البسيط)", 
        "Perfekt (الماضي التام)", 
        "المعنى بالعربية", 
        "مثال سياقي (Beispiel)"
    ]
    for i, h in enumerate(headers):
        hdr[i].text = h

    sample_rows = [
        ("1", "abschließen", "schloss ab", "hat abgeschlossen", "يُنهي / يُبرم (عقداً)", "Er schloss sein Studium erfolgreich ab."),
        ("2", "ablehnen", "lehnte ab", "hat abgelehnt", "يرفض", "Die Firma hat den Antrag abgelehnt."),
        ("3", "anbieten", "bot an", "hat angeboten", "يعرض / يُقدّم", "Das Unternehmen bot ihm eine neue Stelle an."),
        ("4", "die Herausforderung", "-", "-", "التحدي / الصعوبة الكبيرة", "Das ist eine große Herausforderung für uns."),
        ("5", "zuverlässig", "-", "-", "موثوق به / يُعتمد عليه", "Er ist ein sehr zuverlässiger Kollege.")
    ]

    for row_data in sample_rows:
        row = table.add_row().cells
        for i, val in enumerate(row_data):
            row[i].text = val

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    return Response(
        content=bio.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": 'attachment; filename="Vocab_Template.docx"'
        }
    )
