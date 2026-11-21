import io
import pytest
from fastapi.testclient import TestClient
import docx
from pypdf import PdfWriter

from app.main import app
from app.db import init_db, get_db
from app.services.seeder import seed_werkstatt_b2
from app.services.extractor import (
    clean_for_tts,
    clean_for_youglish,
    extract_from_docx,
    extract_from_pdf,
    extract_vocabulary_from_file
)
from app.services.gemini_enricher import build_fallback_examples, rule_based_verb_check
from app.services.html_exporter import generate_standalone_html
from app.telegram_backup import create_safe_sqlite_backup


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    seed_werkstatt_b2()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_clean_for_tts_and_youglish():
    assert clean_for_tts("Chefsekretärin, -nen") == "Chefsekretärin"
    assert clean_for_tts("her/richten") == "herrichten"
    assert clean_for_tts("sich ein/fügen in + AKK") == "sich einfügen in"
    assert clean_for_tts("-n") == "Endung n"
    assert clean_for_tts("der/das Safe") == "der Safe"

    assert clean_for_youglish("der Kommilitone") == "Kommilitone"
    assert clean_for_youglish("die Charakterbildung") == "Charakterbildung"
    assert clean_for_youglish("sich einfügen") == "einfügen"


def test_rule_based_verb_check():
    is_v, perf = rule_based_verb_check("aus/führen")
    assert is_v is True
    assert "ausführen" in perf

    is_v2, perf2 = rule_based_verb_check("weg/brechen")
    assert is_v2 is True
    assert "ist" in perf2

    examples = build_fallback_examples("herrichten", "herrichten", "يجهز", "vorbereiten")
    assert len(examples) == 3
    assert examples[0]["tag"] == "سياق B2 تطبيقي"


def test_docx_extractor():
    doc = docx.Document()
    table = doc.add_table(rows=1, cols=3)
    hdr = table.rows[0].cells
    hdr[0].text = "Deutsch"
    hdr[1].text = "Arabisch"
    hdr[2].text = "Seite"

    row = table.add_row().cells
    row[0].text = "her/richten"
    row[1].text = "يصلح ويجهز"
    row[2].text = "5"

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    items = extract_from_docx(bio.getvalue())
    assert len(items) == 1
    assert items[0]["word"] == "her/richten"
    assert items[0]["arabic"] == "يصلح ويجهز"
    assert items[0]["page"] == 5


def test_pdf_extractor():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    bio = io.BytesIO()
    writer.write(bio)
    bio.seek(0)

    # Empty blank page returns empty list without error
    items = extract_from_pdf(bio.getvalue())
    assert isinstance(items, list)


def test_standalone_html_export():
    html = generate_standalone_html(1)
    assert "<!DOCTYPE html>" in html
    assert "قاموس" in html
    assert "embedded-data" in html
    assert "Chefsekretärin" in html


def test_safe_sqlite_backup():
    backup_file = create_safe_sqlite_backup()
    assert backup_file.exists()
    assert backup_file.name.endswith(".db.gz")
    assert backup_file.stat().st_size > 500


def test_api_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "app": "vocab_tutor"}


def test_api_documents(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) >= 1
    assert docs[0]["title"] == "Werkstatt B2 (563 كلمة)"
    assert docs[0]["total_words"] == 563


def test_api_words_and_filtering(client):
    res = client.get("/api/documents/1/words?status=all&sort=original")
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] == 563
    first_word = data["words"][0]
    assert first_word["word"] == "Chefsekretärin, -nen"

    # Default alphabetical sort
    res_alpha = client.get("/api/documents/1/words?status=all")
    assert res_alpha.status_code == 200
    assert res_alpha.json()["words"][0]["word"] == "abarbeiten"

    # Filter verbs
    res_verbs = client.get("/api/documents/1/words?status=verbs")
    assert res_verbs.status_code == 200
    verbs_data = res_verbs.json()
    assert verbs_data["total_count"] > 50
    assert all(w["is_verb"] or w["perfekt"] for w in verbs_data["words"])

    # Search filter
    res_search = client.get("/api/documents/1/words?q=Sauerstoff")
    assert res_search.status_code == 200
    assert len(res_search.json()["words"]) >= 1


def test_api_learned_and_review_toggle(client):
    # Ensure fresh baseline
    client.post("/api/documents/1/reset-progress")

    # Toggle learned
    res1 = client.post("/api/words/1/learned")
    assert res1.status_code == 200
    assert res1.json()["is_learned"] is True

    # Toggle review
    res2 = client.post("/api/words/1/review")
    assert res2.status_code == 200
    assert res2.json()["is_review"] is True

    # Check words query reflects changes
    res3 = client.get("/api/documents/1/words?status=learned")
    assert any(w["id"] == 1 for w in res3.json()["words"])

    # Reset progress
    res4 = client.post("/api/documents/1/reset-progress")
    assert res4.status_code == 200


def test_api_upload_docx(client):
    doc = docx.Document()
    table = doc.add_table(rows=1, cols=2)
    hdr = table.rows[0].cells
    hdr[0].text = "Deutsch"
    hdr[1].text = "Arabisch"

    r1 = table.add_row().cells
    r1[0].text = "auf/stehen"
    r1[1].text = "يستيقظ"

    r2 = table.add_row().cells
    r2[0].text = "die Prüfung, -en"
    r2[1].text = "الامتحان"

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    files = {"file": ("test_wortliste.docx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res = client.post("/api/upload", data={"title": "Test Liste"}, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["total_words"] == 2
    assert body["title"] == "Test Liste"

    # Clean up test document
    if "document_id" in body:
        client.delete(f"/api/documents/{body['document_id']}")


def test_api_backup_status(client):
    res = client.get("/api/backup/status")
    assert res.status_code == 200
    data = res.json()
    assert "total_backups" in data
    assert data["total_backups"] >= 1


def test_block_format_docx_extraction():
    doc = docx.Document()
    doc.add_paragraph("الحافظة الذكية الدائمة — مصحح الألمانية")
    doc.add_paragraph("إجمالي الكلمات: 2")
    doc.add_paragraph("1. الكلمة / الجملة الألمانية: Ich habe Angst.")
    doc.add_paragraph("الترجمة بالعربي: أنا خائف.")
    doc.add_paragraph("الشرح والملاحظات: • تستخدم مع حالة Akk.")
    doc.add_paragraph("• (1) Ich habe immer Angst vor Hunden.")
    doc.add_paragraph("الترجمة: أنا دائما أخاف من الكلاب.")
    doc.add_paragraph("____________________________________________________________")
    doc.add_paragraph("2. الكلمة / الجملة الألمانية: zufriedenstellend")
    doc.add_paragraph("الترجمة بالعربي: مقنع / مرضي")

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    items = extract_from_docx(bio.getvalue())
    assert len(items) == 2
    assert items[0]["word"] == "Ich habe Angst."
    assert items[0]["arabic"] == "أنا خائف."
    assert len(items[0]["examples"]) >= 2
    assert items[1]["word"] == "zufriedenstellend"
    assert items[1]["arabic"] == "مقنع / مرضي"


def test_six_column_verbs_docx_extraction():
    doc = docx.Document()
    # Add a title table (1 row 1 col) that should be skipped
    doc.add_table(rows=1, cols=1).rows[0].cells[0].text = "أهم الأفعال في الماضي"

    table = doc.add_table(rows=1, cols=6)
    hdr = table.rows[0].cells
    hdr[0].text = "#"
    hdr[1].text = "Infinitiv (المصدر)"
    hdr[2].text = "Präteritum (er/sie/es)"
    hdr[3].text = "Perfekt (hat / ist + P.II)"
    hdr[4].text = "المعنى بالعربية"
    hdr[5].text = "مثال في الماضي (B2)"

    r1 = table.add_row().cells
    r1[0].text = "1"
    r1[1].text = "abschließen"
    r1[2].text = "schloss ab"
    r1[3].text = "hat abgeschlossen"
    r1[4].text = "يُنهي / يُبرم (عقداً)"
    r1[5].text = "Er schloss sein Studium erfolgreich ab."

    r2 = table.add_row().cells
    r2[0].text = "2"
    r2[1].text = "ablehnen"
    r2[2].text = "lehnte ab"
    r2[3].text = "hat abgelehnt"
    r2[4].text = "يرفض"
    r2[5].text = "Die Firma hat den Antrag abgelehnt."

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    items = extract_from_docx(bio.getvalue())
    assert len(items) == 2
    # Verify word is NOT the row number "1"
    assert items[0]["word"] == "abschließen"
    assert items[0]["arabic"] == "يُنهي / يُبرم (عقداً)"
    assert items[0]["perfekt"] == "hat abgeschlossen"
    assert items[0]["praeteritum"] == "schloss ab"
    assert len(items[0]["examples"]) == 1
    assert "Er schloss sein Studium" in items[0]["examples"][0]["de"]

    assert items[1]["word"] == "ablehnen"
    assert items[1]["arabic"] == "يرفض"
    assert items[1]["perfekt"] == "hat abgelehnt"
    assert items[1]["praeteritum"] == "lehnte ab"


def test_download_docx_template(client):
    res = client.get("/api/upload/template/docx")
    assert res.status_code == 200
    assert len(res.content) > 1000
    assert "attachment" in res.headers.get("content-disposition", "")


def test_dual_persistence_and_sync_endpoints(client):
    # 1. Test toggle with explicit state idempotency
    res_l1 = client.post("/api/words/1/learned?state=true")
    assert res_l1.status_code == 200
    assert res_l1.json()["is_learned"] is True

    # Repeated true does not flip back
    res_l2 = client.post("/api/words/1/learned?state=true")
    assert res_l2.status_code == 200
    assert res_l2.json()["is_learned"] is True

    res_l3 = client.post("/api/words/1/learned?state=false")
    assert res_l3.status_code == 200
    assert res_l3.json()["is_learned"] is False

    # 2. Test bulk sync progress
    sync_payload = {
        "learned_ids": [1, 2],
        "review_ids": [2, 3]
    }
    res_sync = client.post("/api/documents/1/sync-progress", json=sync_payload)
    assert res_sync.status_code == 200
    assert res_sync.json()["status"] == "success"

    # Verify status in words list
    res_words = client.get("/api/documents/1/words?status=all")
    assert res_words.status_code == 200
    words_map = {w["id"]: w for w in res_words.json()["words"]}
    assert words_map[1]["is_learned"] is True
    assert words_map[2]["is_learned"] is True
    assert words_map[2]["is_review"] is True
    assert words_map[3]["is_review"] is True

    # 3. Test clear-review endpoint
    res_clear_rev = client.post("/api/documents/1/clear-review")
    assert res_clear_rev.status_code == 200
    assert res_clear_rev.json()["status"] == "success"

    # Verify reviews are cleared but learned status remains
    res_words_after = client.get("/api/documents/1/words?status=all")
    words_map_after = {w["id"]: w for w in res_words_after.json()["words"]}
    assert words_map_after[1]["is_learned"] is True
    assert words_map_after[2]["is_learned"] is True
    assert words_map_after[2]["is_review"] is False
    assert words_map_after[3]["is_review"] is False

    # Cleanup reset progress
    client.post("/api/documents/1/reset-progress")


@pytest.mark.anyio
async def test_auto_translation_enrichment_for_missing_arabic():
    from app.services.gemini_enricher import enrich_vocabulary_batch
    raw_verbs = [
        {"word": "abnehmen", "arabic": "", "synonym": "+D+A", "page": 2, "examples": [{"tag": "مثال", "de": "Ich nehme dir den Koffer ab.", "ar": ""}]},
        {"word": "abtrocknen", "arabic": "", "synonym": "+A", "page": 2, "examples": [{"tag": "مثال", "de": "Sie trocknet das Geschirr ab.", "ar": ""}]}
    ]
    enriched = await enrich_vocabulary_batch(raw_verbs)
    assert len(enriched) == 2
    # Verify non-empty Arabic translation with multiple meanings
    assert enriched[0]["arabic"]
    assert "ينقص" in enriched[0]["arabic"] or "يأخذ" in enriched[0]["arabic"] or "يخفف" in enriched[0]["arabic"]
    assert enriched[0]["perfekt"] == "hat abgenommen"
    assert enriched[0]["praeteritum"] == "nahm ab"
    # Verify example translation
    assert enriched[0]["examples"][0]["ar"]


def test_pdf_case_pattern_extraction():
    from app.services.extractor import parse_lines_to_vocab
    sample_lines = [
        ("abnehmen +D+A Ich nehme dir den Koffer ab.", 2),
        ("abtrocknen +A Sie trocknet das Geschirr ab.", 2),
        ("anschauen (+D)+A Ich schaue mir den neuen Film an.", 2)
    ]
    items = parse_lines_to_vocab(sample_lines)
    assert len(items) == 3
    assert items[0]["word"] == "abnehmen"
    assert items[0]["synonym"] == "+D+A"
    assert items[0]["examples"][0]["de"] == "Ich nehme dir den Koffer ab."
    assert items[2]["word"] == "anschauen"
    assert items[2]["synonym"] == "(+D)+A"


def test_page_relative_word_numbering(client):
    """
    Verifies that with sort=original, word numbering starts strictly from 1
    up to the last word on that page, and does NOT expose raw database IDs.
    """
    res = client.get("/api/documents/1/words?page=all&sort=original")
    assert res.status_code == 200
    words = res.json()["words"]

    # Group words by page and verify each page starts at 1
    from collections import defaultdict
    page_words = defaultdict(list)
    for w in words:
        page_words[w["page"]].append(w)

    for p, p_list in page_words.items():
        assert p_list[0]["page_word_num"] == 1, f"Page {p} should start numbering at 1"
        for idx, item in enumerate(p_list, 1):
            assert item["page_word_num"] == idx, f"Word {idx} on page {p} has incorrect page_word_num"

    # Specific page query test
    res_p2 = client.get("/api/documents/1/words?page=2&sort=original")
    assert res_p2.status_code == 200
    words_p2 = res_p2.json()["words"]
    assert words_p2[0]["page_word_num"] == 1

    res_p3 = client.get("/api/documents/1/words?page=3&sort=original")
    assert res_p3.status_code == 200
    words_p3 = res_p3.json()["words"]
    assert words_p3[0]["page_word_num"] == 1

    # Verify HTML exporter includes page_word_num
    from app.services.html_exporter import generate_standalone_html
    html_out = generate_standalone_html(1)
    assert "page_word_num" in html_out


def test_alphabetical_word_ordering_and_numbering(client):
    """
    Verifies that with sort=alpha, word numbering starts from 1
    and proceeds in strict alphabetical order (A to Z) until the last word.
    """
    # 1. Test Document 1 (Werkstatt B2)
    res1 = client.get("/api/documents/1/words?sort=alpha")
    assert res1.status_code == 200
    words1 = res1.json()["words"]
    assert len(words1) == 563
    assert words1[0]["word"] == "abarbeiten"
    assert words1[0]["page_word_num"] == 1
    assert words1[-1]["word"] == "Zypern"
    assert words1[-1]["page_word_num"] == 563

    for idx, w in enumerate(words1, 1):
        assert w["page_word_num"] == idx

    # 2. Test Document 16 (Verben mit Dativ und Akkusativ) if present
    res16 = client.get("/api/documents/16/words?sort=alpha")
    if res16.status_code == 200:
        words16 = res16.json()["words"]
        assert len(words16) == 252
        assert words16[0]["word"] == "abnehmen"
        assert words16[0]["page_word_num"] == 1
        assert words16[-1]["word"] == "zerstören"
        assert words16[-1]["page_word_num"] == 252


def test_dropdown_case_options_and_sorting(client):
    """
    Verifies that the dropdown options for Akkusativ only and Dativ only
    return strictly the matching verbs with continuous sequential numbering.
    """
    from app.routers.vocab import classify_case

    # Unit checks on classification
    assert classify_case("+A") == "akk"
    assert classify_case("+AKK") == "akk"
    assert classify_case("+ AKK") == "akk"
    assert classify_case("+D") == "dat"
    assert classify_case("+DAT") == "dat"
    assert classify_case("+ DAT") == "dat"
    assert classify_case("+D+A") == "both"
    assert classify_case("(+D)+A") == "both"
    assert classify_case("+D(+A)") == "both"
    assert classify_case("", "helfen (+D)") == "dat"
    assert classify_case("", "helfen", is_verb=True) == "dat"
    assert classify_case("", "schenken", is_verb=True) == "both"
    assert classify_case("", "ertragen", is_verb=True) == "akk"
    assert classify_case("", "existieren", is_verb=True) == "none"
    assert classify_case("Kein Fall", "Buch") == "none"
    assert classify_case("sich ein/fügen in + AKK") == "akk"
    assert classify_case("bei/tragen zu + DAT") == "dat"
    assert classify_case("beitragen zu", is_verb=True) == "dat"

    # Create self-contained test document with mixed cases
    doc = docx.Document()
    table = doc.add_table(rows=1, cols=3)
    hdr = table.rows[0].cells
    hdr[0].text = "Verb"
    hdr[1].text = "Kasus"
    hdr[2].text = "Bedeutung"

    test_data = [
        ("helfen", "+D", "يساعد"),
        ("sehen", "+A", "يرى"),
        ("schenken", "+D+A", "يهدي"),
        ("antworten", "+D", "يجيب"),
        ("fragen", "+A", "يسأل"),
        ("geben", "(+D)+A", "يعطي"),
        ("das Buch", "Nomen", "كتاب"),
    ]
    for v, k, b in test_data:
        r = table.add_row().cells
        r[0].text = v
        r[1].text = k
        r[2].text = b

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    files = {"file": ("cases_dropdown_test.docx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res_up = client.post("/api/upload", data={"title": "Cases Dropdown Test"}, files=files)
    assert res_up.status_code == 200
    doc_id = res_up.json()["document_id"]

    try:
        # 1. Akkusativ only option (sort=akk_only)
        res_akk = client.get(f"/api/documents/{doc_id}/words?sort=akk_only")
        assert res_akk.status_code == 200
        words_akk = res_akk.json()["words"]
        assert len(words_akk) == 2  # fragen, sehen
        assert all(w["grammatical_case"] == "akk" for w in words_akk)
        assert words_akk[0]["page_word_num"] == 1
        assert words_akk[1]["page_word_num"] == 2

        # 2. Dativ only option (sort=dat_only)
        res_dat = client.get(f"/api/documents/{doc_id}/words?sort=dat_only")
        assert res_dat.status_code == 200
        words_dat = res_dat.json()["words"]
        assert len(words_dat) == 2  # antworten, helfen
        assert all(w["grammatical_case"] == "dat" for w in words_dat)
        assert words_dat[0]["page_word_num"] == 1
        assert words_dat[1]["page_word_num"] == 2

        # 3. Both only option (sort=both_only)
        res_both = client.get(f"/api/documents/{doc_id}/words?sort=both_only")
        assert res_both.status_code == 200
        words_both = res_both.json()["words"]
        assert len(words_both) == 2  # geben, schenken
        assert all(w["grammatical_case"] == "both" for w in words_both)

        # 4. Grouped mode (sort=akk_then_dat)
        res_grouped = client.get(f"/api/documents/{doc_id}/words?sort=akk_then_dat")
        assert res_grouped.status_code == 200
        words_grouped = res_grouped.json()["words"]
        assert len(words_grouped) == 7
        for idx, w in enumerate(words_grouped, 1):
            assert w["page_word_num"] == idx
        # Akkusativ first, then both, then Dativ, then none
        assert words_grouped[0]["grammatical_case"] == "akk"
        assert words_grouped[1]["grammatical_case"] == "akk"
        assert words_grouped[2]["grammatical_case"] == "both"
        assert words_grouped[3]["grammatical_case"] == "both"
        assert words_grouped[4]["grammatical_case"] == "dat"
        assert words_grouped[5]["grammatical_case"] == "dat"
        assert words_grouped[6]["grammatical_case"] == "none"

    finally:
        client.delete(f"/api/documents/{doc_id}")


def test_frontend_javascript_syntax_validity_and_cache_headers(client):
    """
    Guarantees that index.html contains valid JavaScript syntax,
    preventing any frontend white-screen syntax regressions, and checks
    anti-caching headers and dynamic version API.
    """
    import subprocess
    import re
    from pathlib import Path

    # 1. Verify index.html Cache-Control headers
    res = client.get("/")
    assert res.status_code == 200
    cache_control = res.headers.get("cache-control", "")
    assert "no-cache" in cache_control
    assert "no-store" in cache_control

    # 2. Verify /api/version
    v_res = client.get("/api/version")
    assert v_res.status_code == 200
    version_data = v_res.json()
    assert "version" in version_data
    assert version_data["version"].startswith("v") or len(version_data["version"]) > 0

    # 3. Validate all inline scripts in index.html with Node.js syntax checker
    index_path = Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")

    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", content, re.DOTALL)
    assert len(scripts) >= 1, "Expected at least 1 inline script in index.html"

    for idx, script_body in enumerate(scripts):
        proc = subprocess.run(
            ["node", "--check", "-"],
            input=script_body,
            text=True,
            capture_output=True
        )
        assert proc.returncode == 0, f"Script block #{idx} in index.html has syntax error:\n{proc.stderr}"


def test_case_options_always_available_across_all_documents(client):
    """
    Guarantees that Akkusativ and Dativ filtering and classification
    function across all documents (including Doc 1 Werkstatt B2),
    and that HTML options are always visible.
    """
    from pathlib import Path

    # Check Doc 1 (Werkstatt B2) has classified Akkusativ and Dativ verbs
    res_doc1 = client.get("/api/documents/1/words")
    assert res_doc1.status_code == 200
    words = res_doc1.json()["words"]
    akk_words = [w for w in words if w["grammatical_case"] == "akk"]
    dat_words = [w for w in words if w["grammatical_case"] == "dat"]
    assert len(akk_words) > 0, "Doc 1 must have classified Akkusativ verbs"
    assert len(dat_words) > 0, "Doc 1 must have classified Dativ verbs"

    # Filter Doc 1 with sort=akk_only
    res_akk = client.get("/api/documents/1/words?sort=akk_only")
    assert res_akk.status_code == 200
    akk_sorted = res_akk.json()["words"]
    assert len(akk_sorted) == len(akk_words)
    assert all(w["grammatical_case"] == "akk" for w in akk_sorted)
    for idx, w in enumerate(akk_sorted, 1):
        assert w["page_word_num"] == idx

    # Filter Doc 1 with sort=dat_only
    res_dat = client.get("/api/documents/1/words?sort=dat_only")
    assert res_dat.status_code == 200
    dat_sorted = res_dat.json()["words"]
    assert len(dat_sorted) == len(dat_words)
    assert all(w["grammatical_case"] == "dat" for w in dat_sorted)
    for idx, w in enumerate(dat_sorted, 1):
        assert w["page_word_num"] == idx

    # Verify options in index.html are not hidden
    index_path = Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
    content = index_path.read_text(encoding="utf-8")
    assert 'value="akk_only"' in content
    assert 'value="dat_only"' in content
    assert 'value="both_only"' in content
    assert 'value="akk_then_dat"' in content
    # Ensure options are not hidden in updateCountsAndBadges
    assert 'optAkk.hidden = true' not in content
    assert 'optDat.hidden = true' not in content


