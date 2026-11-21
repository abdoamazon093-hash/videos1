import io
from typing import List
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from app.models import ClipItem

def set_cell_rtl(cell):
    tcPr = cell._element.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcMar')
    tcPr.append(tcBorders)

def set_paragraph_rtl(p):
    pPr = p._element.get_or_add_pPr()
    bidi = OxmlElement('w:bidi')
    pPr.append(bidi)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

def generate_docx_bytes(clips: List[ClipItem]) -> io.BytesIO:
    doc = Document()

    # هوامش مريحة
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # 1. العنوان الرئيسي
    p_title = doc.add_paragraph()
    set_paragraph_rtl(p_title)
    r_title = p_title.add_run("الحافظة الدائمة — مصحح الألمانية السياقي (B2 - C1 - C2)")
    r_title.font.name = "Arial"
    r_title.font.size = Pt(18)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(124, 58, 237)  # Violet

    # 2. ملخص الإحصائيات
    p_meta = doc.add_paragraph()
    set_paragraph_rtl(p_meta)
    r_meta = p_meta.add_run(f"إجمالي الكلمات والجمل المحفوظة: {len(clips)} عنصر")
    r_meta.font.name = "Arial"
    r_meta.font.size = Pt(12)
    r_meta.font.bold = True
    r_meta.font.color.rgb = RGBColor(5, 150, 105)  # Emerald

    doc.add_paragraph("____________________________________________________________")

    # 3. العناصر
    for idx, c in enumerate(clips, 1):
        # الكلمة الألمانية
        p_de = doc.add_paragraph()
        p_de.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_num = p_de.add_run(f"{idx}. ")
        r_num.font.bold = True
        r_num.font.color.rgb = RGBColor(124, 58, 237)
        r_de = p_de.add_run(c.text)
        r_de.font.name = "Arial"
        r_de.font.size = Pt(14)
        r_de.font.bold = True
        r_de.font.color.rgb = RGBColor(15, 23, 42)

        # الترجمة بالعربي
        p_ar = doc.add_paragraph()
        set_paragraph_rtl(p_ar)
        r_ar_lbl = p_ar.add_run("الترجمة: ")
        r_ar_lbl.font.bold = True
        r_ar_lbl.font.color.rgb = RGBColor(5, 150, 105)
        r_ar_val = p_ar.add_run(c.arabic_meaning or "غير محدد")
        r_ar_val.font.size = Pt(12)
        r_ar_val.font.name = "Arial"

        # ملاحظات الجرامر إن وجدت
        if c.grammar_notes:
            p_notes = doc.add_paragraph()
            set_paragraph_rtl(p_notes)
            r_notes = p_notes.add_run(f"الملاحظات: {c.grammar_notes}")
            r_notes.font.size = Pt(10.5)
            r_notes.font.italic = True
            r_notes.font.color.rgb = RGBColor(71, 85, 105)

        # الأمثلة العملية
        if c.examples:
            p_ex_title = doc.add_paragraph()
            set_paragraph_rtl(p_ex_title)
            r_ex_lbl = p_ex_title.add_run("الأمثلة:")
            r_ex_lbl.font.bold = True
            r_ex_lbl.font.size = Pt(11)
            r_ex_lbl.font.color.rgb = RGBColor(180, 83, 9)  # Amber

            for ex_i, ex in enumerate(c.examples, 1):
                p_ex = doc.add_paragraph()
                p_ex.alignment = WD_ALIGN_PARAGRAPH.LEFT
                r_ex_de = p_ex.add_run(f"  • {ex.de}\n")
                r_ex_de.font.bold = True
                r_ex_de.font.size = Pt(10.5)

                p_ex_ar = doc.add_paragraph()
                set_paragraph_rtl(p_ex_ar)
                r_ex_ar = p_ex_ar.add_run(f"    الترجمة: {ex.ar}")
                r_ex_ar.font.size = Pt(10)
                r_ex_ar.font.color.rgb = RGBColor(100, 116, 139)

        doc.add_paragraph("– – – – – – – – – – – – – – – – – – – – – – – – – – – – – – – – – – – –")

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
