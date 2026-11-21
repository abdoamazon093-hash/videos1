import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import docx
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Removes irregular whitespace and control characters."""
    if not text:
        return ""
    text = re.sub(r'[\r\t]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_for_tts(raw_word: str) -> str:
    """
    Cleans a German vocabulary headword so it sounds natural in Web Speech TTS.
    Removes grammatical markers (+ AKK, + DAT), parens, slashes, and trailing hyphens.
    """
    if not raw_word:
        return ""
    w = raw_word.strip()
    if w == "-n":
        return "Endung n"
    if w.lower() == "der/das safe":
        return "der Safe"
    if w.startswith("auf Trab bringen"):
        return "auf Trab bringen"
    if w == "(wieder)erkennbar":
        return "wiedererkennbar"
    if w == "vormachen (sich)":
        return "sich vormachen"
    if w == "(sich) wühlen":
        return "sich wühlen"

    # Remove leading numbering like "1. ", "2) "
    w = re.sub(r'^\d+[\.\)\-]\s*', '', w)
    # Remove parentheses content e.g. (sich)
    w = re.sub(r'\([^)]*\)', ' ', w)
    # Remove cases e.g. + AKK, + DAT, + GEN
    w = re.sub(r'\+\s*(AKK|DAT|GEN)\b', '', w, flags=re.IGNORECASE)
    w = w.replace("+", " ")
    # Remove comma and everything after if it is grammatical e.g. "Chefsekretärin, -nen" -> "Chefsekretärin"
    w = re.sub(r',.*$', '', w)
    # Remove slashes e.g. her/richten -> herrichten
    w = w.replace("/", "")
    # Remove trailing hyphens
    w = re.sub(r'-+$', '', w)
    w = re.sub(r'\s+', ' ', w).strip()
    return w


def clean_for_youglish(spoken_word: str) -> str:
    """Strips leading articles and reflexive pronouns for clean YouGlish search."""
    if not spoken_word:
        return ""
    return re.sub(r'^(der|die|das|sich|eine|ein)\s+', '', spoken_word, flags=re.IGNORECASE).strip()


def extract_from_docx(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extracts vocabulary lines or table cells from a .docx document.
    Handles:
    1. Tables with columns (German, Arabic, page, etc.)
    2. Multi-line structured entries (e.g. German Coach export blocks: "1. الكلمة: ... \n الترجمة: ...")
    3. Delimited lines ("word - translation" or "word | translation" or "word : translation")
    """
    doc = docx.Document(io.BytesIO(file_bytes))
    extracted: List[Dict[str, Any]] = []

    # Strategy 1: First scan all tables
    for table in doc.tables:
        rows = table.rows
        if len(rows) < 2 or len(table.columns) < 2:
            continue  # Skip single-cell banners or non-vocabulary tables

        # Find header row in first 3 rows
        header_row_idx = -1
        de_col_idx = -1
        ar_col_idx = -1
        perf_col_idx = -1
        praet_col_idx = -1
        ex_col_idx = -1
        page_col_idx = -1
        syn_col_idx = -1

        for r_idx, r in enumerate(rows[:3]):
            cells_text = [clean_text(c.text).lower() for c in r.cells]
            curr_de = -1
            curr_ar = -1
            curr_perf = -1
            curr_praet = -1
            curr_ex = -1
            curr_page = -1
            curr_syn = -1

            for c_idx, h in enumerate(cells_text):
                # Never treat row numbering columns as vocabulary headword
                if h in ["#", "nr", "no", "num", "م", "الرقم", "id"]:
                    continue
                # Example column
                if any(k in h for k in ["beispiel", "satz", "مثال", "سياق", "جملة"]):
                    curr_ex = c_idx
                # Perfekt column
                elif any(k in h for k in ["perfekt", "الماضي التام", "p.ii", "partizip"]):
                    curr_perf = c_idx
                # Präteritum column
                elif any(k in h for k in ["präteritum", "praeteritum", "الماضي البسيط"]):
                    curr_praet = c_idx
                # Arabic translation column
                elif any(k in h for k in ["arabisch", "bedeutung", "ترجمة", "المعنى", "العربية"]) or bool(re.search(r'\bar\b', h)):
                    curr_ar = c_idx
                # German headword column
                elif any(k in h for k in ["infinitiv", "verb", "wort", "deutsch", "german", "الكلمة", "المصدر", "الفعل", "الألمانية"]) or bool(re.search(r'\bde\b', h)):
                    if curr_de == -1:
                        curr_de = c_idx
                # Page column
                elif any(k in h for k in ["seite", "page", "صفحة"]) or bool(re.search(r'\bص\b', h)):
                    curr_page = c_idx
                # Synonym / Case column
                elif any(k in h for k in ["synonym", "مرادف", "بديل", "kasus", "fall", "حالة", "جر", "نصب"]):
                    curr_syn = c_idx

            if curr_de != -1 and curr_ar != -1:
                header_row_idx = r_idx
                de_col_idx = curr_de
                ar_col_idx = curr_ar
                perf_col_idx = curr_perf
                praet_col_idx = curr_praet
                ex_col_idx = curr_ex
                page_col_idx = curr_page
                syn_col_idx = curr_syn
                break

        # If no explicit header found, default to col 0 / col 1 unless col 0 is numbering
        if header_row_idx == -1:
            first_cells = [clean_text(c.text) for c in rows[0].cells]
            if len(first_cells) >= 2:
                second_cells = [clean_text(c.text) for c in rows[1].cells] if len(rows) > 1 else []
                if second_cells and second_cells[0].isdigit():
                    de_col_idx = 1
                    ar_col_idx = 2 if len(second_cells) > 2 else 1
                else:
                    de_col_idx = 0
                    ar_col_idx = 1
            header_row_idx = 0

        current_page = 1
        for row in rows[header_row_idx + 1:]:
            cells = [clean_text(c.text) for c in row.cells]
            if not cells or len(cells) <= max(de_col_idx, ar_col_idx):
                continue

            de_val = cells[de_col_idx] if len(cells) > de_col_idx else ""
            ar_val = cells[ar_col_idx] if len(cells) > ar_col_idx else ""

            # Skip if de_val is just a number, empty, or repeated header
            if not de_val or de_val.isdigit() or de_val.lower() in ["#", "infinitiv", "wort", "deutsch", "verb"]:
                continue

            perf_val = cells[perf_col_idx] if perf_col_idx != -1 and len(cells) > perf_col_idx else ""
            praet_val = cells[praet_col_idx] if praet_col_idx != -1 and len(cells) > praet_col_idx else ""
            ex_val = cells[ex_col_idx] if ex_col_idx != -1 and len(cells) > ex_col_idx else ""
            syn_val = cells[syn_col_idx] if syn_col_idx != -1 and len(cells) > syn_col_idx else ""

            if page_col_idx != -1 and len(cells) > page_col_idx and cells[page_col_idx].isdigit():
                current_page = int(cells[page_col_idx])

            examples = []
            if ex_val:
                examples.append({
                    "tag": "مثال سياقي (B2)",
                    "de": ex_val,
                    "ar": ""
                })

            extracted.append({
                "word": de_val,
                "arabic": ar_val,
                "page": current_page,
                "synonym": syn_val,
                "perfekt": perf_val,
                "praeteritum": praet_val,
                "is_verb": True if (perf_val or praet_val or "verb" in de_val.lower()) else False,
                "examples": examples
            })

    if extracted:
        return extracted

    # Strategy 2: Scan paragraphs for structured blocks (e.g. exported study lists)
    paras = [clean_text(p.text) for p in doc.paragraphs if clean_text(p.text)]
    
    # Check if this document contains numbered blocks like "1. الكلمة / الجملة الألمانية:" or "1. Wort:"
    is_block_format = any(
        re.search(r'^\d+[\.\)]\s*(?:الكلمة|الجملة|Wort|Satz|المصطلح)', p)
        for p in paras
    )

    if is_block_format:
        current_block: Optional[Dict[str, Any]] = None
        for p in paras:
            # Skip title / summary headers / dividers
            if any(skip in p for skip in ["الحافظة الذكية", "إجمالي الكلمات", "المحفوظة:"]):
                continue
            if re.match(r'^_{3,}$', p) or p == "الأمثلة التطبيقية:":
                continue

            # Start of a new vocabulary item: matches "1. الكلمة / الجملة الألمانية: ...", "2. Wort: ...", etc.
            m = re.match(r'^\d+[\.\)]\s*(?:الكلمة|الجملة|Wort|Satz|المصطلح).*?[:\-]\s*(.*)$', p, re.IGNORECASE)
            if m:
                if current_block and current_block.get("word"):
                    extracted.append(current_block)
                w_val = m.group(1).strip()
                current_block = {
                    "word": w_val,
                    "arabic": "",
                    "page": 1,
                    "synonym": "",
                    "notes": "",
                    "examples": []
                }
                continue

            if not current_block:
                continue

            # Translation line (الترجمة بالعربي: ...)
            if re.match(r'^(?:الترجمة|المعنى|Bedeutung)(?:\s*بالعربي)?\s*[:\-]\s*(.*)$', p, re.IGNORECASE):
                t_val = re.sub(r'^(?:الترجمة|المعنى|Bedeutung)(?:\s*بالعربي)?\s*[:\-]\s*', '', p, flags=re.IGNORECASE).strip()
                if not current_block["arabic"]:
                    current_block["arabic"] = t_val
                elif current_block["examples"] and not current_block["examples"][-1].get("ar"):
                    # This is the translation of the last added German example!
                    current_block["examples"][-1]["ar"] = t_val
                else:
                    current_block["examples"].append({"de": "", "ar": t_val, "tag": "مثال"})
            # Notes or synonyms (الشرح والملاحظات: ...)
            elif re.match(r'^(?:الشرح\s*(?:و\s*)?الملاحظات|الشرح|الملاحظات|المرادفات|Synonyme?)\s*[:\-]\s*(.*)$', p, re.IGNORECASE):
                n_val = re.sub(r'^(?:الشرح\s*(?:و\s*)?الملاحظات|الشرح|الملاحظات|المرادفات|Synonyme?)\s*[:\-]\s*', '', p, flags=re.IGNORECASE).strip()
                current_block["notes"] = n_val
                if "مرادف" in p or "synonym" in p.lower():
                    current_block["synonym"] = n_val
                elif n_val:
                    current_block["examples"].append({
                        "de": "💡 ملاحظات وسياق الاستخدام",
                        "ar": n_val,
                        "tag": "ملاحظة"
                    })
            # Example lines starting with bullet
            elif p.startswith("•") or p.startswith("-") or re.match(r'^\s*•\s*\(\d+\)', p):
                ex_de = re.sub(r'^[•\-\*]\s*(?:\(\d+\)\s*)?', '', p).strip()
                current_block["examples"].append({"de": ex_de, "ar": "", "tag": "مثال"})

        if current_block and current_block.get("word"):
            extracted.append(current_block)

        if extracted:
            return extracted

    # Strategy 3: Standard line-by-line delimiter scanning
    current_page = 1
    for text in paras:
        # Check if line is a page indicator e.g. "Seite 12"
        page_match = re.search(r'^(?:seite|page|صفحة)\s*[:\-]?\s*(\d+)$', text, re.IGNORECASE)
        if page_match:
            current_page = int(page_match.group(1))
            continue

        # Skip document titles / banners
        if any(skip in text for skip in ["الحافظة الذكية", "إجمالي الكلمات", "الأمثلة التطبيقية", "سجل الحفظ"]):
            continue

        parts = [clean_text(s) for s in re.split(r'\t|\||(?<=[^\s])\s*[-–—:]\s*(?=[^\s])', text) if clean_text(s)]
        if len(parts) >= 2:
            extracted.append({
                "word": parts[0],
                "arabic": parts[1],
                "page": current_page,
                "synonym": parts[2] if len(parts) > 2 else ""
            })
        elif len(parts) == 1 and len(parts[0]) > 2 and not parts[0].startswith("•"):
            extracted.append({
                "word": parts[0],
                "arabic": "",
                "page": current_page,
                "synonym": ""
            })

    return extracted


def parse_lines_to_vocab(lines_with_page: List[tuple[str, int]]) -> List[Dict[str, Any]]:
    """
    Parses extracted raw text lines (from PdfReader or OCR) into structured vocabulary items.
    Handles:
    1. 'Verb Fall Beispielsatz' tables (e.g. 'abnehmen +D+A Ich nehme dir den Koffer ab.')
    2. Hashtag format (e.g. '#abhängig_von +Dativ معتمد على') with bullet examples
    3. Pipe-separated lines (e.g. 'Word | Translation | Synonym')
    4. Tab or dash-delimited lines (e.g. 'das Buch - الكتاب')
    5. Sentence continuations across lines
    """
    extracted: List[Dict[str, Any]] = []
    last_item: Optional[Dict[str, Any]] = None

    # Matches: <verb> <case> <example>
    # Case variants: +D+A, (+D)+A, +D(+A), +A, +D, + Akk, + Dat, etc.
    case_regex = re.compile(
        r'^([a-zA-ZäöüÄÖÜß,\s\(\)\/]+?)\s+'
        r'(\(\+?\s*[DAda]\)\s*\+?\s*[DAda]|\+?\s*[DAda]\s*\(\+?\s*[DAda]\)|\+?\s*(?:Akk|Dat|Dativ|Akkusativ|D|A)\s*\+?\s*(?:Akk|Dat|Dativ|Akkusativ|D|A)?|\+?\s*[DAda])\s+'
        r'(.+)$'
    )

    for line, page_num in lines_with_page:
        l = clean_text(line)
        if not l:
            continue

        # Skip headers / banners / page numbers
        if any(h in l.lower() for h in ['verb fall beispielsatz', 'verben mit', 'akkusativ', 'dativ', '@marodeutsch']):
            continue
        if l.isdigit() and len(l) <= 3:
            continue

        # Skip cover page banners / watermarks on page 1 if not a vocabulary entry
        if page_num == 1 and (l.isupper() or any(w in l.lower() for w in ['verben', 'akkusativ', 'dativ', 'marodeutsch', 'sauliv'])):
            continue

        # 1. Verb + Case + Example
        m = case_regex.match(l)
        if m:
            verb = clean_text(m.group(1))
            case = clean_text(m.group(2))
            example = clean_text(m.group(3))
            verb = re.sub(r'^[#•\-\*]\s*', '', verb).strip()

            item = {
                'word': verb,
                'arabic': '',
                'page': page_num,
                'synonym': case,
                'is_verb': True,
                'perfekt': '',
                'praeteritum': '',
                'examples': [{
                    'tag': f'مثال سياقي ({case})',
                    'de': example,
                    'ar': ''
                }]
            }
            extracted.append(item)
            last_item = item
            continue

        # 2. Check continuation of example sentence
        if last_item and len(l.split()) <= 6 and not any(l.startswith(c) for c in ['+', '(', '#', '•']):
            if last_item.get('examples'):
                last_item['examples'][0]['de'] += ' ' + l
            continue

        # 3. Hashtag pattern e.g. #abhängig_von +Dativ معتمد على
        m_tag = re.search(r'#([a-zA-ZäöüÄÖÜß_]+)(?:\s*(\+?\s*(?:Dativ|Akkusativ|D|A)))?\s*([\u0600-\u06FF\s\/]+)?', l)
        if m_tag and not any(skip in l.lower() for skip in ['adektive', 'adjektive', 'alle']):
            raw_w = m_tag.group(1).replace('_', ' ')
            prep_c = (m_tag.group(2) or '').strip()
            ar = (m_tag.group(3) or '').strip()
            item = {
                'word': raw_w,
                'synonym': prep_c,
                'arabic': ar,
                'page': page_num,
                'is_verb': False,
                'examples': []
            }
            extracted.append(item)
            last_item = item
            continue

        # Example bullets for hashtag items
        if last_item and ('▪' in l or l.startswith('•')):
            clean_ex = re.sub(r'^[▪•\-\*]\s*', '', l).strip()
            m_split = re.search(r'^([a-zA-ZäöüÄÖÜß0-9\s\.,!\?=\(\)\-–]+?)\s+([\u0600-\u06FF].*)$', clean_ex)
            if m_split:
                de_s = m_split.group(1).strip()
                ar_s = m_split.group(2).strip()
                last_item.setdefault('examples', []).append({'tag': 'مثال سياقي', 'de': de_s, 'ar': ar_s})
            else:
                last_item.setdefault('examples', []).append({'tag': 'مثال سياقي', 'de': clean_ex, 'ar': ''})
            continue

        # 4. Pipe delimiter
        if '|' in l:
            parts = [clean_text(p) for p in l.split('|') if clean_text(p)]
            if len(parts) >= 5:
                p_num = int(parts[1]) if parts[1].isdigit() else page_num
                extracted.append({
                    'word': parts[3],
                    'arabic': parts[4],
                    'page': p_num,
                    'synonym': parts[5] if len(parts) > 5 else ''
                })
                last_item = None
                continue
            elif len(parts) >= 2:
                extracted.append({
                    'word': parts[0],
                    'arabic': parts[1],
                    'page': page_num,
                    'synonym': parts[2] if len(parts) > 2 else ''
                })
                last_item = None
                continue

        # 5. Standard Tab or Dash delimiter
        parts = [clean_text(p) for p in re.split(r'\t|(?<=[^\s])\s*[-–—:]\s*(?=[^\s])', l) if clean_text(p)]
        if len(parts) >= 2:
            extracted.append({
                'word': parts[0],
                'arabic': parts[1],
                'page': page_num,
                'synonym': parts[2] if len(parts) > 2 else ''
            })
            last_item = None
            continue
        elif len(parts) == 1 and len(parts[0]) > 2 and not parts[0].startswith('•') and not any(skip in parts[0] for skip in ['Seite', 'page', 'اللهم']):
            extracted.append({
                'word': parts[0],
                'arabic': '',
                'page': page_num,
                'synonym': ''
            })
            last_item = None

    return extracted


def extract_from_pdf_ocr(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Renders PDF pages as high-resolution images and runs Tesseract OCR (German).
    Used as an automatic fallback for image-based or scanned PDFs where PdfReader extracts no text.
    """
    import tempfile
    import subprocess
    import glob

    logger.info("Running OCR extraction on PDF document using pdftoppm + tesseract...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pdf = Path(tmpdir) / "input.pdf"
        tmp_pdf.write_bytes(file_bytes)

        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "150", str(tmp_pdf), f"{tmpdir}/page"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"pdftoppm execution failed: {e}")
            return []

        page_files = sorted(
            glob.glob(f"{tmpdir}/page-*.png"),
            key=lambda x: int(re.search(r'-(\d+)\.png', x).group(1)) if re.search(r'-(\d+)\.png', x) else 0
        )

        lines_with_page: List[tuple[str, int]] = []
        for pf in page_files:
            m = re.search(r'-(\d+)\.png', pf)
            p_num = int(m.group(1)) if m else 1
            txt_out = f"{tmpdir}/ocr_{p_num}"
            try:
                subprocess.run(
                    ["tesseract", pf, txt_out, "-l", "deu", "--psm", "6"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                ocr_file = Path(f"{txt_out}.txt")
                if ocr_file.exists():
                    with open(ocr_file, encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            lines_with_page.append((line, p_num))
            except Exception as e:
                logger.warning(f"Tesseract OCR failed on page {p_num}: {e}")

        return parse_lines_to_vocab(lines_with_page)


def extract_from_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extracts vocabulary lines from a PDF document, preserving page numbers and formatting.
    Automatically detects scanned / image-based PDFs and uses high-speed OCR fallback.
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    lines_with_page: List[tuple[str, int]] = []

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        text = page.extract_text()
        if not text:
            continue
        for line in text.splitlines():
            lines_with_page.append((line, page_num))

    # If text is present, try parsing
    extracted: List[Dict[str, Any]] = []
    if lines_with_page:
        extracted = parse_lines_to_vocab(lines_with_page)

    # If text extraction produced no items (or PDF is purely image-based like scanned books)
    if len(extracted) < 2:
        logger.info(f"PdfReader extracted insufficient items ({len(extracted)}). Falling back to OCR...")
        ocr_extracted = extract_from_pdf_ocr(file_bytes)
        if ocr_extracted:
            return ocr_extracted

    return extracted


def extract_vocabulary_from_file(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Main ingestion dispatcher for .docx, .pdf, or .txt.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        return extract_from_docx(file_bytes)
    elif ext == ".pdf":
        return extract_from_pdf(file_bytes)
    elif ext in [".txt", ".tsv", ".csv"]:
        text = file_bytes.decode("utf-8", errors="ignore")
        lines = [clean_text(l) for l in text.splitlines() if clean_text(l)]
        items = []
        for line in lines:
            parts = [clean_text(p) for p in line.split("|" if "|" in line else "\t")]
            if len(parts) >= 2:
                items.append({
                    "word": parts[0],
                    "arabic": parts[1],
                    "page": 1,
                    "synonym": parts[2] if len(parts) > 2 else ""
                })
        return items
    else:
        raise ValueError(f"Unsupported file format: {ext}. Please upload .docx, .pdf, or .txt.")
