import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from app.db import get_db

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[Dict[str, Any]])
def list_documents():
    """Lists all available documents/books with stats."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.id, d.title, d.filename, d.file_type, d.total_words, d.created_at,
                   COUNT(CASE WHEN p.is_learned = 1 THEN 1 END) as learned_count,
                   COUNT(CASE WHEN p.is_review = 1 THEN 1 END) as review_count
            FROM documents d
            LEFT JOIN vocabulary_words w ON d.id = w.document_id
            LEFT JOIN user_progress p ON w.id = p.word_id
            GROUP BY d.id
            ORDER BY d.id ASC
        """).fetchall()

        return [
            {
                "id": r["id"],
                "title": r["title"],
                "filename": r["filename"],
                "file_type": r["file_type"],
                "total_words": r["total_words"],
                "created_at": r["created_at"],
                "learned_count": r["learned_count"],
                "review_count": r["review_count"]
            }
            for r in rows
        ]


@router.get("/{document_id}")
def get_document(document_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)


@router.delete("/{document_id}")
def delete_document(document_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT id, title FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        if document_id == 1:
            raise HTTPException(status_code=400, detail="لا يمكن حذف كتاب Werkstatt B2 الأساسي المرجعي.")
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return {"status": "success", "message": f"Document {document_id} deleted."}
