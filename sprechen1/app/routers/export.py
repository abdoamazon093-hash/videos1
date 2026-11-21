import io
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from app.db import get_db
from app.services.html_exporter import generate_standalone_html

router = APIRouter(prefix="/api/documents", tags=["export"])


@router.get("/{document_id}/export/html")
def export_html(document_id: int):
    """Downloads the 100% self-contained standalone offline HTML file."""
    try:
        html_content = generate_standalone_html(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    with get_db() as conn:
        doc = conn.execute("SELECT title FROM documents WHERE id = ?", (document_id,)).fetchone()
        title = doc["title"] if doc else f"vocab_doc_{document_id}"

    safe_title = re.sub(r'[^\w\-_\. ]', '_', title)
    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.html"'
        }
    )


@router.get("/{document_id}/export/docx")
def export_docx(document_id: int):
    """Generates a professional Word .docx table of the vocabulary."""
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        words = conn.execute("""
            SELECT * FROM vocabulary_words WHERE document_id = ? ORDER BY id ASC
        """, (document_id,)).fetchall()

    document = docx.Document()

    # Title
    p = document.add_paragraph()
    run = p.add_run(f"قاموس ومفردات: {doc['title']}")
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = RGBColor(2, 132, 199)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = document.add_paragraph()
    sub_run = sub.add_run(f"إجمالي الكلمات: {len(words)} | تم الإنشاء بواسطة Vocab Tutor")
    sub_run.font.size = Pt(11)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Table
    table = document.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Light Grid Accent 1'

    hdr_cells = table.rows[0].cells
    headers = ["#", "ص", "الكلمة الألمانية (مع البيرفكت)", "الترجمة العربية", "المرادفات"]
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for r in hdr_cells[i].paragraphs[0].runs:
            r.font.bold = True
            r.font.size = Pt(10)

    from app.routers.vocab import german_sort_key
    sorted_words = sorted(words, key=lambda w: german_sort_key(w["word"]))
    for idx, w in enumerate(sorted_words, 1):
        row_cells = table.add_row().cells
        row_cells[0].text = str(idx)
        row_cells[1].text = str(w["page_number"])
        de_text = w["word"]
        if w["perfekt"]:
            de_text += f"\n[Perfekt: {w['perfekt']}]"
        row_cells[2].text = de_text
        row_cells[3].text = w["arabic"]
        row_cells[4].text = w["synonym"] or "-"

    bio = io.BytesIO()
    document.save(bio)
    bio.seek(0)

    safe_title = re.sub(r'[^\w\-_\. ]', '_', doc["title"])
    return Response(
        content=bio.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.docx"'
        }
    )
