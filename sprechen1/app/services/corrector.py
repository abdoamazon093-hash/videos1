import re
from typing import List, Dict, Any, Tuple
from app.models import ReplacementItem, RadarRule, ClipExample

# ==================== القواميس اللغوية المصححة ====================

INSTANT_WORD_ARABIC_DICT: Dict[str, str] = {
    "ich": "أنا", "du": "أنتَ / أنتِ", "er": "هو", "sie": "هي / هم / حضرتك", "es": "هو/هي (لغير العاقل)",
    "wir": "نحن", "ihr": "أنتم", "mein": "ملكي / خاصتي", "meine": "ملكي / خاصتي", "meinem": "ملكي (مجرور)",
    "meinen": "ملكي (مفعول/جمع)", "dein": "ملكك", "deine": "ملكك", "sein": "ملكه / يكون", "seine": "ملكه",
    "unser": "ملكنا", "unsere": "ملكنا", "mir": "لي / إليّ", "dir": "لك / إليك", "mich": "إياي / نفسي",
    "dich": "إياك / نفسك", "uns": "لنا / أنفسنا", "euch": "لكم / أنفسكم",
    "hallo": "مرحباً", "entschuldigung": "معذرةً / عفواً", "bitte": "من فضلك / عفواً", "danke": "شكراً",
    "ja": "نعم", "nein": "لا", "okay": "حسناً / تمام", "gut": "جيد", "sehr": "جداً", "super": "رائع جداً",
    "bruder": "أخ", "schwester": "أخت", "vater": "أب", "mutter": "أم", "eltern": "الوالدين",
    "freund": "صديق", "freundin": "صديقة", "kollege": "زميل", "chef": "مدير / رئيس",
    "familie": "عائلة", "kind": "طفل", "kinder": "أطفال", "mensch": "إنسان", "leute": "ناس",
    "möchte": "أودّ / أرغب", "möchtest": "تودّ / ترغب", "möchten": "نودّ / يرغبون",
    "will": "أريد / يريد", "willst": "تريد", "wollen": "نريد / يريدون",
    "kann": "أستطيع / يستطيع", "kannst": "تستطيع", "können": "نستطيع / يستطيعون",
    "muss": "يجب عليّ / يجب عليه", "musst": "يجب عليك", "müssen": "يجب علينا",
    "soll": "ينبغي", "darf": "يُسمح لي", "werde": "سوف / أصبح", "wird": "سوف / يصبح",
    "habe": "لديّ / عندي (أو فعل مساعد للماضي)", "hast": "لديك / عندك", "hat": "لديه / عنده", "haben": "لدينا / يملكون",
    "bin": "أكون", "bist": "تكون", "ist": "يكون / تكون", "sind": "نكون / يكونون", "seid": "تكونون",
    "war": "كان / كنتُ", "waren": "كانوا / كنا", "wäre": "سيكون (افتراضي)",
    "sprechen": "يتحدث / التحدث", "spreche": "أتحدث", "sprichst": "تتحدث",
    "unterhalten": "يتجاذب أطراف الحديث / يتحاور", "sagen": "يقول / قول", "sage": "أقول",
    "gespräch": "محادثة / حوار", "meinung": "رأي / وجهة نظر", "frage": "سؤال", "antwort": "إجابة",
    "bereit": "مستعد / جاهز", "lust": "رغبة / شهية", "angst": "خوف / قلق", "zeit": "وقت",
    "heute": "اليوم", "gestern": "أمس", "morgen": "غداً / صباحاً", "vorhin": "قبل قليل / منذ لحظات",
    "jetzt": "الآن", "gerade": "حالياً / للتو", "immer": "دائماً", "oft": "غالباً", "manchmal": "أحياناً",
    "schon": "بالفعل / من قبل", "noch": "ما زال / بعد", "wieder": "مرة أخرى", "später": "لاحقاً",
    "ungefähr": "تقريباً / حوالي", "etwa": "حوالي", "fast": "تقريباً / كاد",
    "ein": "واحد / أداة نكرة", "eine": "واحدة / أداة نكرة للمؤنث", "einen": "أداة نكرة (مفعول به)",
    "der": "الـ (للمذكر)", "die": "الـ (للمؤنث أو الجمع)", "das": "الـ (للمحايد) / هذا", "dem": "الـ (مجرور Dativ)", "den": "الـ (مفعول/جمع)",
    "und": "وَ (حرف عطف)", "oder": "أو", "aber": "لكن / غير أن", "denn": "لأن",
    "weil": "لأن (ترسل الفعل للنهاية)", "dass": "أنّ (ترسل الفعل للنهاية)", "damit": "لكي / حتى (أو بذلك)",
    "wenn": "عندما / إذا (للتكرار والشرط)", "als": "عندما (لحدث وقع مرة بالماضي)", "ob": "ما إذا / هل",
    "wieso": "لماذا / كيف حدث", "warum": "لماذا", "wie": "كيف", "was": "ماذا / ما", "wer": "مَنْ", "wo": "أين",
    "leider": "للأسف", "vielleicht": "ربما", "natürlich": "طبعاً / بالتأكيد", "wirklich": "حقاً / فعلاً",
    "nicht": "لا / ليس (للنفي)", "kein": "لا يوجد (لنفي الاسم)", "keine": "لا يوجد (للمؤنث والجمع)",
    "webseite": "موقع إلكتروني / صفحة ويب", "website": "موقع إلكتروني", "entworfen": "صمّم / صممتُ (تصريف ثالث)",
    "funktioniert": "يعمل / يشتغل", "funktionieren": "يعمل", "passiert": "حدث / حصل", "passieren": "يحدث",
    "weiß": "أعرف / يعلم", "weißt": "تعرف / تعلم", "wissen": "يعرفون / المعرفة",
    "drei": "ثلاثة (3)", "zwei": "اثنان (2)", "vier": "أربعة (4)", "fünf": "خمسة (5)",
    "monate": "أشهر / شهور", "monaten": "أشهر (في حالة الجر)", "monat": "شهر",
    "tag": "يوم", "tage": "أيام", "woche": "أسبوع", "wochen": "أسابيع", "jahr": "سنة / عام", "jahre": "سنوات",
    "daran": "في ذلك / على ذلك", "darauf": "على ذلك / لهذا الأمر", "dabei": "في ذلك / عندها",
    "gearbeitet": "عملتُ / اشتغلتُ (تصريف ثالث)", "arbeiten": "يعمل", "arbeit": "عمل / وظيفة",
    "ergebnis": "نتيجة", "ergebnisse": "نتائج", "zufrieden": "راضٍ (للأشخاص)", "zufriedenstellend": "مُرضٍ / مُقنع (للنتائج والأشياء)",
    "etwas": "شيء ما / قليلاً", "anders": "بشكل مختلف", "anderes": "شيئاً آخر / مختلفاً",
    "offen": "بصراحة / مفتوح", "behalten": "يحتفظ بـ", "bleiben": "يبقى / يثبت على", "bestehe": "أُصرّ / أتمسك",
    "neues": "جديد", "interessantes": "مثير للاهتمام / شيّق", "führen": "يُجري (حواراً) / يقود",
    "lass": "دعنا / خَلّينا", "dieses": "هذا / هذه", "computer": "حاسوب / كمبيوتر", "laptop": "لابتوب / حاسوب محمول",
    "vor": "أمام / قبل", "mit": "مع / بـ", "für": "من أجل / لـ", "an": "على / في", "in": "في / داخل", "auf": "على / فوق",
    "zu": "إلى / لـ", "von": "من / عن", "bei": "عند / لدى", "nach": "إلى / بعد", "aus": "من (داخل)", "seit": "منذ",
    "sitze": "أجلس", "sitzen": "يجلس", "schlafe": "أنام", "schlafen": "ينام",
    "einschlafe": "أغفو / يدخل في النوم", "eingeschlafen": "غفوتُ / غلبني النوم",
    "verschlafe": "تروح عليّ نومة / أستيقظ متأخراً", "verschlafen": "راحت عليه نومة",
    "trinke": "أشرب", "trinken": "يشرب", "kurz": "قليلاً / باختصار / للحظة", "mal": "مرّة / (ملطف للكلام)"
}

GERMAN_NOUN_DICT: Dict[str, Dict[str, str]] = {
    "bruder": {"p": "Bruder", "g": "m"}, "schwester": {"p": "Schwester", "g": "f"}, "vater": {"p": "Vater", "g": "m"},
    "mutter": {"p": "Mutter", "g": "f"}, "eltern": {"p": "Eltern", "g": "p"}, "familie": {"p": "Familie", "g": "f"},
    "kind": {"p": "Kind", "g": "n"}, "kinder": {"p": "Kinder", "g": "p"}, "freund": {"p": "Freund", "g": "m"},
    "freundin": {"p": "Freundin", "g": "f"}, "kollege": {"p": "Kollege", "g": "m"}, "chef": {"p": "Chef", "g": "m"},
    "arbeit": {"p": "Arbeit", "g": "f"}, "haus": {"p": "Haus", "g": "n"}, "hause": {"p": "Hause", "g": "n"},
    "zeit": {"p": "Zeit", "g": "f"}, "tag": {"p": "Tag", "g": "m"}, "tage": {"p": "Tage", "g": "p"},
    "woche": {"p": "Woche", "g": "f"}, "wochen": {"p": "Wochen", "g": "p"}, "monat": {"p": "Monat", "g": "m"},
    "monate": {"p": "Monate", "g": "p"}, "jahr": {"p": "Jahr", "g": "n"}, "jahre": {"p": "Jahre", "g": "p"},
    "gespräch": {"p": "Gespräch", "g": "n"}, "meinung": {"p": "Meinung", "g": "f"}, "computer": {"p": "Computer", "g": "m"},
    "laptop": {"p": "Laptop", "g": "m"}, "webseite": {"p": "Webseite", "g": "f"}, "website": {"p": "Website", "g": "f"},
    "ergebnis": {"p": "Ergebnis", "g": "n"}, "ergebnisse": {"p": "Ergebnisse", "g": "p"}, "prüfung": {"p": "Prüfung", "g": "f"},
    "thema": {"p": "Thema", "g": "n"}, "entschuldigung": {"p": "Entschuldigung", "g": "f"}
}

# تصحيح الأخطاء اللغوية في تصريفات الأفعال:
# 1. denken: ich: "denke" (تم إصلاحها من "denken")
# 2. brauchen: es: "braucht" (تم إصلاحها من "brauchst")
VERB_CONJUGATIONS: Dict[str, Dict[str, str]] = {
    "sein": {"ich": "bin", "du": "bist", "er": "ist", "es": "ist", "wir": "sind", "ihr": "seid", "sie": "sind", "pp": "gewesen", "aux": "sein"},
    "haben": {"ich": "habe", "du": "hast", "er": "hat", "es": "hat", "wir": "haben", "ihr": "habt", "sie": "haben", "pp": "gehabt", "aux": "haben"},
    "werden": {"ich": "werde", "du": "wirst", "er": "wird", "es": "wird", "wir": "werden", "ihr": "werdet", "sie": "werden", "pp": "geworden", "aux": "sein"},
    "können": {"ich": "kann", "du": "kannst", "er": "kann", "es": "kann", "wir": "können", "ihr": "könnt", "sie": "können", "pp": "gekonnt", "aux": "haben"},
    "müssen": {"ich": "muss", "du": "musst", "er": "muss", "es": "muss", "wir": "müssen", "ihr": "müsst", "sie": "müssen", "pp": "gemusst", "aux": "haben"},
    "wollen": {"ich": "will", "du": "willst", "er": "will", "es": "will", "wir": "wollen", "ihr": "wollt", "sie": "wollen", "pp": "gewollt", "aux": "haben"},
    "sollen": {"ich": "soll", "du": "sollst", "er": "soll", "es": "soll", "wir": "sollen", "ihr": "sollt", "sie": "sollen", "pp": "gesollt", "aux": "haben"},
    "gehen": {"ich": "gehe", "du": "gehst", "er": "geht", "es": "geht", "wir": "gehen", "ihr": "geht", "sie": "gehen", "pp": "gegangen", "aux": "sein"},
    "kommen": {"ich": "komme", "du": "kommst", "er": "kommt", "es": "kommt", "wir": "kommen", "ihr": "kommt", "sie": "kommen", "pp": "gekommen", "aux": "sein"},
    "fahren": {"ich": "fahre", "du": "fährst", "er": "fährt", "es": "fährt", "wir": "fahren", "ihr": "fahrt", "sie": "fahren", "pp": "gefahren", "aux": "sein"},
    "schlafen": {"ich": "schlafe", "du": "schläfst", "er": "schläft", "es": "schläft", "wir": "schlafen", "ihr": "schlaft", "sie": "schlafen", "pp": "geschlafen", "aux": "haben"},
    "einschlafen": {"ich": "schlafe ein", "du": "schläfst ein", "er": "schläft ein", "es": "schläft ein", "wir": "schlafen ein", "ihr": "schlaft ein", "sie": "schlafen ein", "pp": "eingeschlafen", "aux": "sein"},
    "verschlafen": {"ich": "verschlafe", "du": "verschläfst", "er": "verschläft", "es": "verschläft", "wir": "verschlafen", "ihr": "verschlaft", "sie": "verschlafen", "pp": "verschlafen", "aux": "haben"},
    "denken": {"ich": "denke", "du": "denkst", "er": "denkt", "es": "denkt", "wir": "denken", "ihr": "denkt", "sie": "denken", "pp": "gedacht", "aux": "haben"},
    "brauchen": {"ich": "brauche", "du": "brauchst", "er": "braucht", "es": "braucht", "wir": "brauchen", "ihr": "braucht", "sie": "brauchen", "pp": "gebraucht", "aux": "haben"},
    "arbeiten": {"ich": "arbeite", "du": "arbeitest", "er": "arbeitet", "es": "arbeitet", "wir": "arbeiten", "ihr": "arbeitet", "sie": "arbeiten", "pp": "gearbeitet", "aux": "haben"}
}

SEIN_PARTICIPLES = {
    "gegangen", "gefahren", "gekommen", "angekommen", "abgefahren", "mitgefahren",
    "zurückgekommen", "geflogen", "gelaufen", "eingeschlafen", "aufgewacht",
    "aufgestanden", "passiert", "geschehen", "geblieben", "gewesen", "geworden"
}

def clean_punct(s: str) -> str:
    return re.sub(r'^[.!?,،؟;:"“”„()\[\]]+|[.!?,،؟;:"“”„()\[\]]+$', '', s.strip())

def normalize_text(s: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[.!?,،؟;:"“”„()\[\]\-]', ' ', s.lower())).strip()

def dedup_words(text: str) -> str:
    words = text.strip().split()
    if len(words) < 2:
        return text.strip()
    out = []
    for w in words:
        cw = clean_punct(w).lower()
        prev = clean_punct(out[-1]).lower() if out else ""
        if cw and cw == prev and cw not in {"sehr", "ganz", "viel", "bitte", "ja", "nein"}:
            continue
        out.append(w)
    return " ".join(out)

def run_local_corrector(text: str) -> Tuple[str, List[ReplacementItem]]:
    s = dedup_words(text)
    replacements: List[ReplacementItem] = []

    def record_rep(wrong: str, right: str, why: str, ex: str = ""):
        if wrong and right and normalize_text(wrong) != normalize_text(right):
            if not any(normalize_text(r.wrong_or_arabic) == normalize_text(wrong) for r in replacements):
                replacements.append(ReplacementItem(
                    wrong_or_arabic=wrong.strip(),
                    right_german=right.strip(),
                    why_replaced=why,
                    example=ex
                ))

    # 1. إزالة روابط الاستفهام الزائدة في البداية
    if re.match(r'^oder\s+(?=(?:ich|du|er|sie|wir|ihr|bist|hast|kannst|hallo)\b)', s, re.I):
        s = re.sub(r'^oder\s+', '', s, flags=re.I)
        record_rep("oder", "(حذف رابط زائد)", "حذف رابط استفتاحي زائد في بداية الجملة.", "Ich möchte mal mit dir sprechen.")

    # 2. ضمير يعود على die Webseite ومنع تكرار aber
    if re.search(r'\b(eine\s+(?:Webseite|Website)\s+entworfen,?\s+aber\s+leider\s+funktioniert)\s+das(?:\s+aber)?\s+nicht\b', s, re.I):
        s = re.sub(r'\b(eine\s+(?:Webseite|Website)\s+entworfen,?\s+aber\s+leider\s+funktioniert)\s+das(?:\s+aber)?\s+nicht\b', r'\1 sie nicht', s, flags=re.I)
        record_rep("das aber", "sie", "ضمير يعود على (die Webseite) المؤنثة ومنع تكرار aber.", "Die Webseite ist fertig, aber sie funktioniert nicht.")

    # 3. العبارات العربية العفوية
    if re.search(r'(?:اشرب شويه|أشرب شوية|اشرب ميه)', s):
        s = re.sub(r'(?:اشرب شويه|أشرب شوية|اشرب ميه)', 'Ich trinke kurz etwas.', s)
        record_rep("اشرب شويه", "Ich trinke kurz etwas", "ترجمة العبارة العربية العفوية إلى جملة ألمانية سليمة.", "Warte kurz, ich trinke kurz etwas.")

    # 4. المدة الزمنية بدون حرف جر تأتي Akkusativ
    dur_m = re.search(r'(?:^|[\s,;:.!?])(?:(seit|vor|in|nach|mit)\s+)?(ein|zwei|drei|vier|fünf)\s+(Monaten|Tagen|Jahren|Wochen)\b', s, re.I)
    if dur_m and not dur_m.group(1):
        num, unit = dur_m.group(2), dur_m.group(3)
        clean_unit = re.sub(r'n$', '', unit, flags=re.I)
        proper_unit = clean_unit.capitalize()
        s = s.replace(f"{num} {unit}", f"{num} {proper_unit}")
        record_rep(f"{num} {unit}", f"{num} {proper_unit}", "المدة الزمنية بدون حرف جر تأتي Akkusativ (بدون n).", f"Ich habe {num} {proper_unit} daran gearbeitet.")

    # 5. تقديم الفعل في المركز الثاني (Inversion) بعد الظرف leider
    if re.search(r'\b(aber\s+leider|leider)\s+(die|der|das)\s+([A-ZÄÖÜa-zäöüß]+)\s+(waren|war|sind|ist)\b', s, re.I):
        def inv_sub(m):
            adv, art, noun, verb = m.group(1), m.group(2).lower(), m.group(3).capitalize(), m.group(4)
            return f"{adv} {verb} {art} {noun}"
        before_inv = s
        s = re.sub(r'\b(aber\s+leider|leider)\s+(die|der|das)\s+([A-ZÄÖÜa-zäöüß]+)\s+(waren|war|sind|ist)\b', inv_sub, s, flags=re.I)
        record_rep("die Ergebnisse waren", "waren die Ergebnisse", "تقديم الفعل في المركز الثاني (V2) بعد الظرف leider.", "Aber leider waren die Ergebnisse nicht gut.")

    # 6. النتائج zufriedenstellend وليست zufrieden
    if re.search(r'\b(Ergebnisse|Resultate|Webseite)\s+(?:waren|war|sind|ist)\s+nicht\s+zufrieden\b', s, re.I):
        s = re.sub(r'\b(Ergebnisse|Resultate|Webseite\s+(?:waren|war|sind|ist)\s+nicht\s+)zufrieden\b', r'\1zufriedenstellend', s, flags=re.I)
        record_rep("zufrieden", "zufriedenstellend", "النتائج «مُرضية» (zufriedenstellend)، بينما (zufrieden) للشخص الراضي.", "Die Ergebnisse waren leider nicht zufriedenstellend.")

    # 7. أفعال الحركة وتغير الحالة تأخذ sein وليس haben
    sein_match = re.search(r'\b(ich|du|er|sie|es|wir|ihr)\s+(habe|hast|hat|haben|habt)\s+((?:schon\s+|gestern\s+|früher\s+)?)(eingeschlafen|gegangen|gefahren|gekommen)\b', s, re.I)
    if sein_match:
        pron = sein_match.group(1).lower()
        mid = sein_match.group(3)
        participle = sein_match.group(4).lower()
        sein_map = {"ich": "bin", "du": "bist", "er": "ist", "sie": "ist", "es": "ist", "wir": "sind", "ihr": "seid"}
        aux = sein_map.get(pron, "bin")
        full_wrong = f"{sein_match.group(1)} {sein_match.group(2)} {mid}{participle}"
        full_right = f"{pron.capitalize()} {aux} {mid}{participle}"
        s = s.replace(sein_match.group(0), full_right)
        record_rep(full_wrong, full_right, "أفعال تغير الحالة والحركة تأخذ المساعد (sein) وليس (haben).", f"{full_right}.")

    # 8. ترتيب الفعل في الجمل الجانبية (Nebensatz mit weil / dass / obwohl)
    # مثال: weil ich war sehr müde -> weil ich sehr müde war
    nebensatz_match = re.search(r'\b(weil|dass|obwohl|wenn)\s+(ich|du|er|sie|es|wir|ihr)\s+(war|bin|ist|habe|hat)\s+([^,.!?]+)\b', s, re.I)
    if nebensatz_match:
        conj, pron, verb, rest = nebensatz_match.group(1), nebensatz_match.group(2), nebensatz_match.group(3), nebensatz_match.group(4).strip()
        orig = f"{conj} {pron} {verb} {rest}"
        fixed = f"{conj} {pron} {rest} {verb}"
        s = s.replace(orig, fixed)
        record_rep(orig, fixed, f"في جملة ({conj}) يذهب الفعل المصرف إلى نهاية الجملة.", f"..., {fixed}.")

    # 9. تكبير الحرف الأول للأسماء الألمانية (Großschreibung)
    words = s.split()
    fixed_words = []
    for i, w in enumerate(words):
        clean_w = clean_punct(w).lower()
        if clean_w in GERMAN_NOUN_DICT:
            proper = GERMAN_NOUN_DICT[clean_w]["p"]
            fixed_w = w.replace(clean_punct(w), proper)
            fixed_words.append(fixed_w)
        elif i == 0 and w and w[0].islower():
            fixed_words.append(w.capitalize())
        else:
            fixed_words.append(w)
    s = " ".join(fixed_words)

    # 10. إضافة علامة ترقيم في النهاية
    if s and s[-1] not in {'.', '!', '?'}:
        is_q = bool(re.match(r'^(hast|bist|kannst|möchtest|willst|wer|was|wo|warum|wieso|wie)\b', s, re.I))
        s += '?' if is_q else '.'

    return s, replacements

def extract_radar_rules(german_text: str) -> List[RadarRule]:
    rules = []
    text_norm = german_text.lower()

    if "leider waren" in text_norm or "vorhin habe ich" in text_norm:
        rules.append(RadarRule(
            segment="leider waren die Ergebnisse",
            level="B2",
            rule_name="تقديم الفعل في المركز الثاني (Inversion - Position 2)",
            explanation="عند بدء الجملة بظرف (leider / vorhin) يتقدم الفعل المصرف فوراً في المركز الثاني قبل الفاعل.",
            examples=[{"de": "Leider waren die Ergebnisse nicht zufriedenstellend.", "ar": "للأسف لم تكن النتائج مرضية."}]
        ))

    if "zufriedenstellend" in text_norm:
        rules.append(RadarRule(
            segment="zufriedenstellend",
            level="B2 / C1",
            rule_name="اسم الفاعل كصفة لغير العاقل (Partizip I)",
            explanation="نستخدم (zufriedenstellend = مُرضٍ) لوصف الأشياء والنتائج، بينما (zufrieden = راضٍ) للإنسان.",
            examples=[{"de": "Wir haben eine zufriedenstellende Lösung gefunden.", "ar": "وجدنا حلاً مُرضياً."}]
        ))

    if "daran" in text_norm or "darauf" in text_norm:
        rules.append(RadarRule(
            segment="daran gearbeitet",
            level="B2",
            rule_name="الظروف الضميرية مع حروف الجر (Pronominaladverbien)",
            explanation="الفعل (arbeiten an + Dat) يستخدم مع غير العاقل الضمير الظرفي (daran = العمل عليه).",
            examples=[{"de": "Ich habe drei Monate daran gearbeitet.", "ar": "عملتُ ثلاثة أشهر على ذلك."}]
        ))

    if re.search(r'\b(weil|obwohl|dass|wenn)\b', text_norm):
        rules.append(RadarRule(
            segment="Nebensatz (weil / dass / obwohl)",
            level="B1 / B2",
            rule_name="موقع الفعل في الجملة الجانبية (Nebensatz Verb-Letzt-Stellung)",
            explanation="الروابط التابعة ترسل الفعل المصرف دائماً إلى أقصى نهاية الجملة.",
            examples=[{"de": "... weil ich sehr müde war.", "ar": "... لأنني كنت متعباً جداً."}]
        ))

    return rules
