import re
from typing import Optional

# German Dativ verbs stems (verbs whose object is Dativ)
DATIV_VERB_STEMS = {
    'antworten', 'ähneln', 'ausweichen', 'befehlen', 'begegnen', 'beistehen', 'beitreten', 
    'beiwohnen', 'danken', 'dienen', 'drohen', 'einfallen', 'entgegenkommen', 'entkommen', 
    'entsprechen', 'fehlen', 'folgen', 'gefallen', 'gehorchen', 'gehören', 'gelingen', 
    'genügen', 'glauben', 'gratulieren', 'helfen', 'nachhelfen', 'missfallen', 'misslingen', 
    'misstrauen', 'nachgeben', 'nachgehen', 'nachlaufen', 'nützen', 'nutzen', 'passen', 
    'reichen', 'schaden', 'schmecken', 'schwerfallen', 'leichtfallen', 'stehen', 'trauen', 
    'vertrauen', 'unterliegen', 'verzeihen', 'wehtun', 'widersprechen', 'widmen', 'zuhören', 
    'zujubeln', 'zureden', 'zusehen', 'zustimmen', 'zuwenden', 'zugutekommen', 'hinterherlaufen',
    'aushelfen', 'beitragen', 'auffallen'
}

# German Dativ + Akkusativ (two-object) verbs stems
BOTH_VERB_STEMS = {
    'abnehmen', 'anbieten', 'beibringen', 'bringen', 'empfehlen', 'erklären', 'erlauben', 
    'erzählen', 'geben', 'leihen', 'mitteilen', 'schenken', 'schicken', 'schreiben', 
    'senden', 'stehlen', 'tragen', 'verbieten', 'versichern', 'versprechen', 'wegnehmen', 
    'zeigen', 'wünschen', 'vorschlagen', 'kaufen', 'verraten', 'liefern', 'vorspielen', 
    'vormachen', 'bereitstellen', 'überlassen', 'ausstellen', 'einbehalten', 'mitbringen'
}

# Pure intransitive verbs without case object
INTRANSITIVE_VERB_STEMS = {
    'existieren', 'schlafen', 'bleiben', 'ankommen', 'abfahren', 'aufwachen', 'sterben', 
    'wachsen', 'geschehen', 'passieren', 'fallen', 'sinken', 'steigen', 'pendeln', 'rosten', 
    'verrotten', 'schrumpfen', 'ausbleiben', 'anhalten', 'qualmen', 'dopen', 'entbrennen'
}


def clean_verb_stem(v: str) -> str:
    """Extracts base normalized verb infinitive stem without prefixes/articles."""
    t = (v or '').lower()
    t = re.sub(r'^[#•\-\*\s]+', '', t)
    for prefix in ['sich ', 'jemandem ', 'etwas ', 'den ']:
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = t.replace('/', '')
    parts = t.split()
    return parts[0] if parts else ''


def classify_case(synonym: str = "", word: str = "", is_verb: bool = False) -> str:
    """
    Classifies grammatical case across all German documents, formats, and verbs:
    - 'both': takes both Dativ and Akkusativ (+D+A, (+D)+A, +D(+A), +A+D, or two-object verbs)
    - 'akk': takes Akkusativ (+A, + AKK, Akkusativ, Akk., or transitive verbs)
    - 'dat': takes Dativ (+D, + DAT, Dativ, Dat., or Dativ verbs/prepositions)
    - 'none': no case indicated
    """
    s = f"{synonym or ''} {word or ''}".upper()

    # 1. Regex checks with flexible spacing, parentheses, and dots
    has_d_explicit = bool(re.search(r'\+\s*D\b|\+\s*DAT\b|\bDATIV\b|\bDAT\.?\b|\(\+?\s*D\b', s))
    has_a_explicit = bool(re.search(r'\+\s*A\b|\+\s*AKK\b|\bAKKUSATIV\b|\bAKK\.?\b|\(\+?\s*A\b', s))

    if has_d_explicit and has_a_explicit:
        return "both"
    elif has_a_explicit:
        return "akk"
    elif has_d_explicit:
        return "dat"

    # Prepositional triggers for verbs
    if is_verb or re.search(r'\b(ZU|VON|BEI|MIT|NACH|AUS|SEIT|FÜR|DURCH|GEGEN|OHNE|UM)\b', s):
        if re.search(r'\b(ZU|VON|BEI|MIT|NACH|AUS|SEIT|GEGENÜBER)\b', s):
            return "dat"
        if re.search(r'\b(FÜR|DURCH|GEGEN|OHNE|UM)\b', s):
            return "akk"

    # 2. German verb lexicons
    w_clean = clean_verb_stem(word)
    if is_verb or (w_clean and w_clean.endswith(('en', 'eln', 'ern'))):
        if w_clean in BOTH_VERB_STEMS:
            return "both"
        if w_clean in DATIV_VERB_STEMS:
            return "dat"
        if w_clean in INTRANSITIVE_VERB_STEMS:
            return "none"
        if is_verb:
            # Transitive verb default in German
            return "akk"

    return "none"
