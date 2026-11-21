import json
import logging
from pathlib import Path
from app.db import get_db
from app.config import DATA_DIR
from app.services.extractor import clean_for_tts, clean_for_youglish
from app.services.gemini_enricher import build_fallback_examples
from app.services.case_classifier import classify_case

logger = logging.getLogger(__name__)

# Complete Perfekt map matching the user's reference HTML
PERFEKT_MAP = {
    3: 'hat hergerichtet',
    4: 'hat ausgeführt',
    10: 'hat beigetragen',
    12: 'hat sich eingefügt',
    14: 'hat existiert',
    21: 'hat verallgemeinert',
    23: 'hat sich verstanden',
    28: 'ist weggebrochen',
    29: 'ist zusammengebrochen',
    31: 'ist geraten',
    41: 'hat eingestellt',
    42: 'hat sich berufen',
    48: 'hat ertragen',
    53: 'hat festgestanden',
    54: 'hat ausgesetzt',
    55: 'hat gedrosselt',
    60: 'hat vertragen',
    61: 'hat getrimmt',
    62: 'ist ins Rollen gekommen',
    63: 'hat angeregt',
    66: 'hat auf Trab gebracht',
    70: 'hat durchblutet',
    72: 'ist abgesackt',
    73: 'hat sich aufgerafft',
    82: 'hat vorgesehen',
    86: 'hat gekillt',
    94: 'hat hinterlegt',
    96: 'hat sich abgespielt',
    100: 'hat eingeschult',
    101: 'hat betreut',
    103: 'ist eingesprungen',
    108: 'hat verschmutzt',
    113: 'hat gefährdet',
    118: 'hat ergeben',
    129: 'hat beeinträchtigt',
    136: 'hat demoralisiert',
    146: 'hat verdrängt',
    148: 'hat entschlüsselt',
    154: 'hat referiert',
    158: 'hat sich die Zeit vertrieben',
    163: 'hat zur Verfügung gestellt',
    166: 'hat ausgeholfen',
    168: 'hat eingehalten',
    172: 'ist übrig geblieben',
    173: 'hat vorgefunden',
    176: 'hat sich zurückgezogen',
    179: 'hat beigetragen',
    181: 'hat abgestreift',
    187: 'hat abgekürzt',
    188: 'hat sich festgesetzt',
    203: 'hat/ist unterlegen',
    208: 'hat entfaltet',
    218: 'hat belächelt',
    219: 'hat ins Lächerliche gezogen',
    231: 'hat sich betragen',
    232: 'hat abgelenkt',
    235: 'ist eingezogen / hat eingezogen',
    238: 'ist untersagt gewesen',
    244: 'hat absorbiert',
    245: 'hat gestört',
    247: 'hat nachgeschlagen',
    253: 'hat geplagt',
    258: 'hat versprüht',
    259: 'hat sich bezogen',
    260: 'hat verschüttet',
    261: 'hat eine Zeitlang angehalten',
    262: 'hat in Gang gesetzt',
    264: 'hat geahnt',
    266: 'hat in den Griff bekommen',
    268: 'hat ein schlechtes Gewissen gehabt',
    269: 'ist auf der Strecke geblieben',
    270: 'ist zu kurz gekommen',
    271: 'hat in Kauf genommen',
    274: 'hat abgearbeitet',
    275: 'hat abgearbeitet',
    278: 'ist zugutegekommen',
    280: 'hat nachgeholt',
    281: 'hat versäumt',
    283: 'hat zittrige Knie bekommen',
    286: 'ist abgewichen',
    291: 'hat den Überblick behalten',
    292: 'hat beeinträchtigt',
    297: 'hat überschritten',
    298: 'hat zerlegt',
    301: 'hat simuliert',
    303: 'ist gescheitert',
    304: 'hat Vaterschaftsurlaub beantragt',
    305: 'hat Anspruch gehabt',
    307: 'hat vereinbart',
    313: 'hat infiziert',
    322: 'ist umgeben gewesen',
    324: 'ist hinterhergelaufen',
    326: 'hat ausgelöst',
    327: 'hat bezweifelt',
    331: 'ist aufgelebt',
    334: 'hat den Fokus gerichtet',
    339: 'hat überstanden',
    340: 'hat gedopt',
    351: 'hat angesetzt',
    352: 'hat bekämpft',
    353: 'hat nachgeholfen',
    354: 'ist herangekommen',
    355: 'ist vorübergegangen',
    356: 'hat entrümpelt',
    359: 'ist ausgegangen',
    362: 'hat bereut',
    363: 'hat hinausgeschoben',
    365: 'hat unterteilt',
    367: 'hat rumgeschleppt',
    369: 'hat sich erwiesen',
    372: 'hat herumgetragen',
    373: 'hat eingespart',
    374: 'hat einen Gefallen getan',
    379: 'hat abgebucht',
    387: 'hat eingeführt',
    392: 'hat angebaut',
    393: 'hat aufgebaut',
    408: 'hat verschoben',
    409: 'hat geblättert',
    410: 'hat durchgesetzt',
    416: 'hat sich vorgemacht',
    420: 'hat geborgen',
    422: 'ist entbrannt',
    424: 'haben zusammengehalten',
    425: 'hat wertgeschätzt',
    432: 'hat sich bemüht',
    435: 'hat abgedichtet',
    436: 'hat aufgebessert',
    437: 'hat gequalmt',
    438: 'hat widerstanden',
    439: 'hat sich ausgesetzt',
    440: 'hat inhaliert',
    445: 'hat hervorgerufen',
    447: 'ist angestiegen',
    454: 'hat in Brand gesetzt',
    455: 'ist abgebrannt / hat abgebrannt',
    456: 'ist verrottet',
    462: 'hat erzielt',
    475: 'ist eingegangen',
    478: 'hat gewahrt',
    479: 'hat geherrscht',
    489: 'hat sich gewühlt',
    494: 'hat einbehalten',
    496: 'hat ausgestellt',
    507: 'hat die Daumen gedrückt',
    514: 'ist ausgeblieben',
    518: 'ist/hat gependelt',
    522: 'hat geschmökert',
    523: 'hat stimuliert',
    525: 'ist entronnen',
    527: 'hat nachgelassen',
    528: 'hat eine neue Existenz aufgebaut',
    530: 'hat plädiert',
    541: 'hat gezüchtet',
    542: 'ist geschrumpft',
    547: 'hat adoptiert',
    549: 'hat verfügt',
    553: 'hat sich zugelegt',
    555: 'hat enttarnt',
    556: 'hat verborgen',
    557: 'hat Anerkennung erlangt',
    560: 'hat benachteiligt',
    562: 'hat vorgespielt'
}


def seed_werkstatt_b2() -> int:
    """Seeds the initial 563 Werkstatt B2 words into the database if not present."""
    data_file = DATA_DIR / "werkstatt_b2.txt"
    if not data_file.exists():
        logger.warning(f"Seed file {data_file} not found.")
        return 0

    with get_db() as conn:
        # Check if Werkstatt B2 document already exists
        cursor = conn.execute("SELECT id FROM documents WHERE title = ?", ("Werkstatt B2 (563 كلمة)",))
        row = cursor.fetchone()
        if row:
            doc_id = row["id"]
            count = conn.execute("SELECT count(*) as c FROM vocabulary_words WHERE document_id = ?", (doc_id,)).fetchone()["c"]
            if count >= 560:
                return count

        # Create document
        cursor = conn.execute(
            "INSERT INTO documents (title, filename, file_type, total_words) VALUES (?, ?, ?, ?)",
            ("Werkstatt B2 (563 كلمة)", "werkstatt_b2.txt", "seed", 563)
        )
        doc_id = cursor.lastrowid

        lines = data_file.read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            parts = line.strip().split("|")
            item_id = int(parts[0])
            page = int(parts[1])
            raw_word = parts[3]
            arabic = parts[4]
            synonym = parts[5] if len(parts) > 5 else ""

            spoken_word = clean_for_tts(raw_word)
            youglish_query = clean_for_youglish(spoken_word)
            perfekt = PERFEKT_MAP.get(item_id, "")
            is_verb = bool(perfekt)
            syn_list = [s.strip() for s in synonym.split("/") if s.strip()] if "/" in synonym else [s.strip() for s in synonym.split(",") if s.strip()]

            c_case = classify_case(synonym, raw_word, is_verb)
            w_cur = conn.execute("""
                INSERT INTO vocabulary_words 
                (document_id, page_number, word, spoken_word, youglish_query, arabic, synonym, synonym_list_json, is_verb, perfekt, grammatical_case)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, page, raw_word, spoken_word, youglish_query, arabic, synonym,
                json.dumps(syn_list, ensure_ascii=False), is_verb, perfekt, c_case
            ))
            word_db_id = w_cur.lastrowid

            # Add default 3 contextual examples
            examples = build_fallback_examples(raw_word, spoken_word, arabic, synonym)
            for idx, ex in enumerate(examples):
                conn.execute("""
                    INSERT INTO word_examples (word_id, tag, de_sentence, ar_sentence, order_index)
                    VALUES (?, ?, ?, ?, ?)
                """, (word_db_id, ex["tag"], ex["de"], ex["ar"], idx))

        conn.execute("UPDATE documents SET total_words = ? WHERE id = ?", (len(lines), doc_id))
        logger.info(f"Seeded {len(lines)} words for document {doc_id}")
        return len(lines)
