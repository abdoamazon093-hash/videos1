import difflib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    """Creates a configured Gemini API client with a 30s network timeout."""
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=30000),
    )


class GeminiKeyMissingError(Exception):
    """Raised when GEMINI_API_KEY is not configured."""
    pass


class GeminiServiceError(Exception):
    """Raised when an error occurs during Gemini API generation or parsing."""
    pass


def compute_word_diff(original: str, corrected: str) -> List[Dict[str, str]]:
    """Generates word-level visual diff tokens for UI (equal, removed, added)."""
    orig_tokens = re.findall(r'\S+|\s+', original)
    corr_tokens = re.findall(r'\S+|\s+', corrected)

    matcher = difflib.SequenceMatcher(None, orig_tokens, corr_tokens)
    diff_tokens: List[Dict[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            text = "".join(orig_tokens[i1:i2])
            if text:
                diff_tokens.append({"type": "equal", "text": text})
        elif tag == "delete":
            text = "".join(orig_tokens[i1:i2])
            if text:
                diff_tokens.append({"type": "removed", "text": text})
        elif tag == "insert":
            text = "".join(corr_tokens[j1:j2])
            if text:
                diff_tokens.append({"type": "added", "text": text})
        elif tag == "replace":
            del_text = "".join(orig_tokens[i1:i2])
            add_text = "".join(corr_tokens[j1:j2])
            if del_text:
                diff_tokens.append({"type": "removed", "text": del_text})
            if add_text:
                diff_tokens.append({"type": "added", "text": add_text})

    return diff_tokens


def _call_gemini_json(
    client: genai.Client,
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.1,
) -> str:
    """
    Executes a Gemini API call optimized for ultra-low latency with zero thinking budget,
    and automatic resilient fallback across supported flash models.
    """
    candidate_models = []
    if GEMINI_MODEL:
        candidate_models.append(GEMINI_MODEL)
    candidate_models.extend(["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"])

    # Unique models preserving order
    seen = set()
    unique_models = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        temperature=temperature,
    )

    last_error = None
    for model_name in unique_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            if response and response.text:
                return response.text
        except APIError as api_err:
            last_error = api_err
            logger.warning(f"Gemini model '{model_name}' encountered APIError: {api_err}. Trying fallback...")
            continue
        except Exception as err:
            last_error = err
            logger.warning(f"Gemini model '{model_name}' failed: {err}. Trying fallback...")
            continue

    raise GeminiServiceError(f"All candidate Gemini models failed. Last error: {last_error}")


# ============================================================================
# 1. 6-Section German Sentence Corrector
# ============================================================================

CORRECTION_SYSTEM_PROMPT = """
Du bist "German Coach" — ein hochpräziser muttersprachlicher Deutschlehrer und Linguist für Niveaustufen B1 bis C2.
Deine Aufgabe ist eine tiefgründige, vierstufige Analyse deutscher Sätze für arabischsprachige Deutschlerner.

### 4 Analyse-Ebenen (STRIKT ZU BEFOLGEN):

1. **Stille ASR-Bereinigung (Silent ASR Cleanup):**
   - Fehler, die rein aus der automatischen Spracherkennung (Speech-to-Text / المايك) resultieren — wie fehlende Kommas, Satzzeichen oder unbeabsichtigte Groß-/Kleinschreibung einzelner Wörter mitten im Satz (z.B. "Sitze" statt "sitze", "hallo" statt "Hallo") — korrigierst du in "direct_correction" und "native_version" STILLSCHWEIGEND.
   - Solche reinen ASR-Phänomene DÜRFEN NICHT in der "errors"-Liste auftauchen und zählen NICHT als Fehler!

2. **Logik- und Arabisch-Interferenz-Radar (Kategorie "logic_l1"):**
   - Prüfe jeden Teilsatz auf logische Stimmigkeit und Realitätsnähe, selbst wenn er grammatisch fehlerfrei wirkt.
   - Entlarve Ausdrücke, die wörtlich aus dem Arabischen/Ägyptischen ins Deutsche übertragen wurden (L1-Interferenz / أفخاخ الترجمة الحرفية من العربي).
   - Setze bei jedem solchen Fund "category": "logic_l1" und "arabic_trap": true.
   - Halte "original" so präzise und isoliert wie möglich auf die falsche Wendung bezogen (z.B. "auf meinem Laptop" -> "am Laptop").
   - Beispiele:
     * "auf meinem Laptop sitzen" -> Logikfehler / Arabische Falle ("قاعد على اللابتوب" بالمصري). Man sitzt "am Laptop" oder "vor meinem Laptop" (nicht physisch auf dem Gerät!). "original": "auf meinem Laptop", "correction": "am Laptop".
     * "hallo und Bruder" oder wörtliches "Hallo mein Bruder" in informellem Kontext -> unidiomatisch / wörtliche Übersetzung ("أهلاً يا أخويا"). Natürlich: "Hey Bro", "Hallo mein Lieber", "Hallo mein Freund" oder einfach "Hey".

3. **Grammatik, Syntax & Konjunktionsschutz (Kategorie "grammar"):**
   - Erfasse echte grammatikalische Fehler: Kasus, Präpositionen, Adjektivendungen ("etwas anders" -> "etwas anderes"), Verwechslung von "wenn" und "wann".
   - **STRIKTER KONJUNKTIONSSCHUTZ:** Entferne NIEMALS sinnvolle Kausal- oder Nebensatz-Konnektoren wie "weil", "obwohl", "dass", um Sätze künstlich zu zerhacken. Behaupte NIEMALS fälschlich einen Fehler bei der Verbstellung, wenn das Verb im Nebensatz bereits am Satzende steht.

4. **Stil, Wiederholung & Satzvervollständigung (Kategorie "style"):**
   - Erfasse unnötige Wort- und Phrasenwiederholungen (z.B. zweifaches "ein nettes Gespräch" in aufeinanderfolgenden Teilsätzen).
   - Unvollständige / abgebrochene Sätze (z.B. "sag mal wenn..."): Korrigiere "wenn" zu "wann" ("grammar") und vervollständige den Gedanken im Kontext natürlich (z.B. "Sag mir bitte Bescheid, wann es dir passt" oder "Sag mal, wann du Zeit hast").

### 2 Lösungsversionen (STRIKT ERFORDERLICH):
1. **"direct_correction"**:
   - Die direkte Korrektur: Bleibt so nah wie möglich am ursprünglichen Wortlaut des Benutzers, behebt aber alle Grammatikfehler, logischen Schnitzer und arabischen Fallen. Konjunktionen (wie "weil") bleiben erhalten.
2. **"native_version"**:
   - Die muttersprachliche Meisterfassung (Authentisches Alltags-/Fachdeutsch): Völlig natürlich und flüssig, frei von redundanten Wiederholungen, elegant formuliert, passend zum gewählten Zielniveau ("level": B1/B2/C1/C2) und der gewählten Höflichkeitsform/Tonalität ("tone": "du" für freundschaftlich/locker oder "Sie" für formell/geschäftlich).

### Konsistenz-Regel:
Jede reale Änderung zwischen dem Text des Benutzers und der "direct_correction" (abgesehen von der stillen ASR-Bereinigung) MUSS zwingend als Eintrag in "errors" dokumentiert sein. Behaupte niemals in "explanation_ar" eine Korrektur, die nicht tatsächlich in "direct_correction" vorgenommen wurde.

Du MUSST ausschließlich ein valides JSON-Objekt mit folgendem Schema zurückgeben:
{
  "direct_correction": "...",
  "native_version": "...",
  "direct_arabic_meaning": "...",
  "native_arabic_meaning": "...",
  "is_correct": false,
  "summary_ar": "ملخص عربي واضح في سطر واحد لأهم الملاحظات والتصحيحات",
  "errors": [
    {
      "original": "الجزء الخطأ بالنص الأصلي",
      "correction": "البديل الصحيح في التصحيح المباشر",
      "category": "grammar",
      "arabic_trap": false,
      "rule_tag": "اسم القاعدة المختصر (مثال: حروف الجر - ترجمة حرفية / نهايات الصفات / الفرق بين wenn و wann)",
      "explanation_ar": "شرح عربي مباشر وواضح",
      "example": "Mustersatz auf Deutsch",
      "example_ar": "ترجمة عربية للمثال"
    }
  ],
  "radar_rules": [
    {
      "segment": "Teil des Satzes",
      "level": "B2",
      "rule_name": "Regelname",
      "explanation": "شرح عربي",
      "example_de": "Beispiel",
      "example_ar": "ترجمة"
    }
  ],
  "contextual_examples": [
    "...", "..."
  ]
}
"""


def correct_sentence(text: str, level: str = "B2", tone: str = "du") -> Dict[str, Any]:
    """
    Corrects a German sentence using the Gemini API and prepares data for the upgraded UI
    with 4-layer analysis, dual solutions (direct & native), and Arabic trap detection.
    """
    if not GEMINI_API_KEY:
        raise GeminiKeyMissingError(
            "GEMINI_API_KEY is not configured in .env. Please set a valid Gemini API key to enable live AI correction."
        )

    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Text cannot be empty.")

    target_level = level.upper()
    if target_level not in {"B1", "B2", "C1", "C2"}:
        target_level = "B2"

    target_tone = "Sie" if tone and tone.lower() == "sie" else "du"
    tone_desc = "Sie (formell/geschäftlich)" if target_tone == "Sie" else "du (freundschaftlich/informell)"

    try:
        client = _get_client()
        user_prompt = f"Zielniveau: {target_level}\nTonalität: {tone_desc}\nEingegebener Satz:\n\"{clean_text}\""

        raw_response = _call_gemini_json(
            client=client,
            prompt=user_prompt,
            system_instruction=CORRECTION_SYSTEM_PROMPT,
            temperature=0.1,
        )

        parsed = json.loads(raw_response or "{}")

        direct_correction = parsed.get("direct_correction") or parsed.get("corrected_text") or clean_text
        direct_correction = direct_correction.strip()

        native_version = parsed.get("native_version") or direct_correction
        native_version = native_version.strip()

        direct_arabic_meaning = (parsed.get("direct_arabic_meaning") or parsed.get("arabic_meaning") or "").strip()
        native_arabic_meaning = (parsed.get("native_arabic_meaning") or direct_arabic_meaning).strip()

        diff_data = compute_word_diff(clean_text, direct_correction)

        errors_raw = parsed.get("errors") or parsed.get("replacements") or []
        radar_rules = parsed.get("radar_rules") or []
        contextual_examples = parsed.get("contextual_examples") or []
        arabic_translations = parsed.get("arabic_translations") or []
        summary_ar = (parsed.get("summary_ar") or "").strip()
        is_correct = bool(parsed.get("is_correct", len(errors_raw) == 0))

        # Normalized errors array with backward-compatible replacements
        errors = []
        replacements = []

        for item in errors_raw:
            orig = (item.get("original") or item.get("wrong") or "").strip()
            corr = (item.get("correction") or item.get("right") or "").strip()
            cat = item.get("category", "grammar")
            if cat not in {"grammar", "logic_l1", "style"}:
                cat = "grammar"

            is_trap = bool(item.get("arabic_trap", False) or cat == "logic_l1")
            r_tag = (item.get("rule_tag") or "").strip()
            expl = (item.get("explanation_ar") or item.get("why") or "").strip()
            ex = (item.get("example") or "").strip()
            ex_ar = (item.get("example_ar") or "").strip()
            right_ar = (item.get("right_ar") or "").strip()

            err_obj = {
                "original": orig,
                "correction": corr,
                "wrong": orig,  # legacy alias
                "right": corr,  # legacy alias
                "right_ar": right_ar,
                "category": cat,
                "arabic_trap": is_trap,
                "rule_tag": r_tag,
                "explanation_ar": expl,
                "why": expl,  # legacy alias
                "example": ex,
                "example_ar": ex_ar,
                "error_text": orig,
                "correction_text": corr,
                "explanation": expl,
            }
            errors.append(err_obj)
            replacements.append(err_obj)

        return {
            "original_text": clean_text,
            "direct_correction": direct_correction,
            "native_version": native_version,
            "corrected_text": direct_correction,  # Legacy alias
            "direct_arabic_meaning": direct_arabic_meaning,
            "native_arabic_meaning": native_arabic_meaning,
            "arabic_meaning": direct_arabic_meaning,  # Legacy alias
            "level": target_level,
            "tone": target_tone,
            "is_correct": is_correct,
            "summary_ar": summary_ar,
            "explanation": summary_ar,  # Backward compatibility
            "errors": errors,
            "replacements": replacements,
            "radar_rules": radar_rules,
            "diff_data": diff_data,
            "arabic_translations": arabic_translations,
            "contextual_examples": contextual_examples,
        }

    except json.JSONDecodeError as jde:
        logger.error(f"Failed to parse Gemini JSON response: {jde}")
        raise GeminiServiceError(f"Invalid JSON returned by Gemini: {str(jde)}") from jde
    except Exception as e:
        logger.error(f"Gemini API request failed: {e}")
        raise GeminiServiceError(f"Gemini API error: {str(e)}") from e


# ============================================================================
# 2. AI Assistant (Section 3 Concise Q&A)
# ============================================================================

ASSISTANT_SYSTEM_PROMPT = """
Du bist ein prägnanter deutscher Sprachassistent für arabischsprachige Deutschlerner (B1-C2).
Beantworte die gestellte Frage zum aktuellen Satz oder zur Grammatik extrem kurz und präzise in 2-3 klaren Punkten auf Arabisch.
Hebe wichtige deutsche Ausdrücke oder Regeln in "german_highlight" hervor und gib 1-2 Mustersätze in "examples".

Antworte ausschließlich im JSON-Format:
{
  "answer_ar": "نص الجواب باختصار شديد وواضح في نقطتين أو ثلاثة باللغة العربية",
  "german_highlight": "التركيب أو القاعدة الألمانية الهامة",
  "examples": [
    "Beispielsatz 1...",
    "Beispielsatz 2..."
  ]
}
"""


def ask_assistant(question: str, current_sentence: Optional[str] = None) -> Dict[str, Any]:
    """
    Answers a learner's quick question about German grammar or the current sentence.
    """
    if not GEMINI_API_KEY:
        raise GeminiKeyMissingError("GEMINI_API_KEY is not configured in .env.")

    clean_q = question.strip()
    if not clean_q:
        raise ValueError("Question cannot be empty.")

    context_prompt = f"Frage des Lernenden: {clean_q}"
    if current_sentence and current_sentence.strip():
        context_prompt += f"\nAktueller Satz im Kontext: \"{current_sentence.strip()}\""

    try:
        client = _get_client()
        raw_response = _call_gemini_json(
            client=client,
            prompt=context_prompt,
            system_instruction=ASSISTANT_SYSTEM_PROMPT,
            temperature=0.1,
        )
        parsed = json.loads(raw_response or "{}")
        return {
            "question": clean_q,
            "answer_ar": parsed.get("answer_ar", "").strip(),
            "german_highlight": parsed.get("german_highlight", "").strip(),
            "examples": parsed.get("examples") or [],
        }
    except Exception as e:
        logger.error(f"AI Assistant failed: {e}")
        raise GeminiServiceError(f"AI Assistant error: {str(e)}") from e


# ============================================================================
# 3. Word Explanation (Section 2 Clickable Word Lookup)
# ============================================================================

WORD_SYSTEM_PROMPT = """
Du bist ein deutsches Fachwörterbuch für arabischsprachige Deutschlerner.
Erkläre das angegebene deutsche Wort präzise:
- "word": Die angefragte Vokabel
- "german_word": Das Wort mit bestimmtem Artikel (falls Substantiv, z.B. "das Ergebnis, -se") oder Grundform
- "arabic_meaning": Die genaueste deutsche Bedeutung auf Arabisch (1-3 Wörter)
- "examples": 2 kurze, alltagsnahe Beispielsätze auf Deutsch mit präziser arabischer Übersetzung.

Antworte ausschließlich im JSON-Format:
{
  "word": "...",
  "german_word": "...",
  "arabic_meaning": "...",
  "examples": [
    {"de": "Beispielsatz 1...", "ar": "الترجمة 1..."},
    {"de": "Beispielsatz 2...", "ar": "الترجمة 2..."}
  ]
}
"""


def explain_word(word: str) -> Dict[str, Any]:
    """
    Retrieves the meaning, article, and examples for a German word.
    """
    if not GEMINI_API_KEY:
        raise GeminiKeyMissingError("GEMINI_API_KEY is not configured in .env.")

    clean_word = word.strip()
    if not clean_word:
        raise ValueError("Word cannot be empty.")

    try:
        client = _get_client()
        prompt = f"Erkläre folgendes Wort: \"{clean_word}\""
        raw_response = _call_gemini_json(
            client=client,
            prompt=prompt,
            system_instruction=WORD_SYSTEM_PROMPT,
            temperature=0.1,
        )
        parsed = json.loads(raw_response or "{}")
        return {
            "word": clean_word.lower(),
            "german_word": parsed.get("german_word", clean_word),
            "arabic_meaning": parsed.get("arabic_meaning", ""),
            "examples": parsed.get("examples") or [],
        }
    except Exception as e:
        logger.error(f"Explain word failed: {e}")
        raise GeminiServiceError(f"Explain word error: {str(e)}") from e


# ============================================================================
# 4. Clip Deep-Explanation (Section 6 Smart Clipboard)
# ============================================================================

CLIP_SYSTEM_PROMPT = """
Du bist ein deutscher Sprachexperte. Analysiere den gespeicherten deutschen Ausdruck/Satz für die persönliche Lern-Hafitha (Clipboard):
- "german_text": Der deutsche Ausdruck in korrekter Form
- "arabic_translation": Präzise arabische Übersetzung
- "grammar_explanation": Kurze grammatikalische / idiomatische Erklärung auf Arabisch (2-3 Zeilen)
- "synonyms": 2-3 nützliche Synonyme oder alternative Ausdrücke
- "examples": 2 Mustersätze mit arabischer Übersetzung

Antworte ausschließlich im JSON-Format:
{
  "german_text": "...",
  "arabic_translation": "...",
  "grammar_explanation": "...",
  "synonyms": ["...", "..."],
  "examples": [
    {"de": "Beispielsatz 1...", "ar": "الترجمة 1..."},
    {"de": "Beispielsatz 2...", "ar": "الترجمة 2..."}
  ]
}
"""


def explain_clip(text: str) -> Dict[str, Any]:
    """
    Deeply analyzes and annotates a saved clip with grammar explanation, synonyms, and examples.
    """
    if not GEMINI_API_KEY:
        raise GeminiKeyMissingError("GEMINI_API_KEY is not configured in .env.")

    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Clip text cannot be empty.")

    try:
        client = _get_client()
        prompt = f"Analysiere folgenden Ausdruck:\n\"{clean_text}\""
        raw_response = _call_gemini_json(
            client=client,
            prompt=prompt,
            system_instruction=CLIP_SYSTEM_PROMPT,
            temperature=0.1,
        )
        parsed = json.loads(raw_response or "{}")
        return {
            "german_text": parsed.get("german_text", clean_text),
            "arabic_translation": parsed.get("arabic_translation", ""),
            "grammar_explanation": parsed.get("grammar_explanation", ""),
            "synonyms": parsed.get("synonyms") or [],
            "examples": parsed.get("examples") or [],
        }
    except Exception as e:
        logger.error(f"Explain clip failed: {e}")
        raise GeminiServiceError(f"Explain clip error: {str(e)}") from e
