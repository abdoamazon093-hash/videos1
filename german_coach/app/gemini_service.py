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
Du bist "German Coach" — ein hochpräziser muttersprachlicher Deutschlehrer für Niveaustufen B1 bis C2.
Deine Aufgaben:
1. Analysiere den deutschen Satz für das Zielniveau (B1, B2, C1 oder C2).
2. Code-Switching / Arabische Wörter: Wenn der Benutzer arabische Wörter mitten im deutschen Satz verwendet hat, übersetze sie nahtlos und idiomatisch in den passenden deutschen Kontext.
3. Korrigiere alle grammatikalischen, syntaktischen und stilistischen Fehler präzise gemäß Zielniveau. Behalte korrekte deutsche Wörter bei (kein unnötiges Ersetzen).
4. Beurteile "is_correct": Setze "is_correct": true, wenn der Satz grammatikalisch und lexikalisch im Wesentlichen korrekt war (ignoriere reine Groß-/Kleinschreibung und Zeichensetzungsunterschiede aus der Spracheingabe). Andernfalls false.
5. "summary_ar": Ein prägnanter, einzeiliger arabischer Satz, der die wichtigste Korrektur zusammenfasst.
6. "replacements": Liste NUR echter Kontext- und Grammatikfehler (OHNE reine Großschreibung und OHNE Kommasetzung):
   - "wrong": Das fehlerhafte Wort oder Segment
   - "right": Die korrekte deutsche Form
   - "why": Kurze Erklärung auf Arabisch (5-8 Wörter)
   - "example": Kurzer alltagsnaher deutscher Mustersatz
   - "category": Eine aus: "Kasus" | "Wortstellung" | "Verb" | "Wortschatz" | "Konjunktion" | "Präposition" | "Adjektivdeklination" | "Passiv" | "Konjunktiv II" | "Sonstiges"
7. "radar_rules": Grammatikregeln und Strukturen im Satz:
   - "segment": Der Teil im Satz
   - "level": B1 | B2 | C1 | C2
   - "rule_name": Name der Regel (z.B. "Nebensatz mit weil", "Dativ nach Präposition mit")
   - "explanation": Kurze Erklärung auf Arabisch
   - "example_de": Mustersatz auf Deutsch
   - "example_ar": Übersetzung des Mustersatzes
8. "arabic_meaning": Natürliche, flüssige arabische Übersetzung des gesamten korrigierten Satzes.
9. "arabic_translations": Liste der übersetzten arabischen Wörter aus dem Satz (falls vorhanden).
10. "contextual_examples": 2 kurze, alltagsnahe deutsche Mustersätze.

Du MUSST ausschließlich ein valides JSON-Objekt zurückgeben:
{
  "corrected_text": "...",
  "arabic_meaning": "...",
  "is_correct": false,
  "summary_ar": "...",
  "replacements": [
    {
      "wrong": "...",
      "right": "...",
      "why": "...",
      "example": "...",
      "category": "Kasus"
    }
  ],
  "radar_rules": [
    {
      "segment": "...",
      "level": "B2",
      "rule_name": "...",
      "explanation": "...",
      "example_de": "...",
      "example_ar": "..."
    }
  ],
  "arabic_translations": [
    {
      "arabic": "...",
      "german": "...",
      "context": "..."
    }
  ],
  "contextual_examples": [
    "...", "..."
  ]
}
"""


def correct_sentence(text: str, level: str = "B2") -> Dict[str, Any]:
    """
    Corrects a German sentence using the Gemini API and prepares data for the 6-section UI.
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

    try:
        client = _get_client()
        user_prompt = f"Zielniveau: {target_level}\nEingegebener Satz:\n\"{clean_text}\""

        raw_response = _call_gemini_json(
            client=client,
            prompt=user_prompt,
            system_instruction=CORRECTION_SYSTEM_PROMPT,
            temperature=0.1,
        )

        parsed = json.loads(raw_response or "{}")

        corrected_text = parsed.get("corrected_text", clean_text).strip()
        diff_data = compute_word_diff(clean_text, corrected_text)

        replacements = parsed.get("replacements") or []
        radar_rules = parsed.get("radar_rules") or []
        arabic_translations = parsed.get("arabic_translations") or []
        contextual_examples = parsed.get("contextual_examples") or []
        arabic_meaning = parsed.get("arabic_meaning", "").strip()
        summary_ar = parsed.get("summary_ar", "").strip()
        is_correct = bool(parsed.get("is_correct", len(replacements) == 0))

        # Backward compatibility with errors list for SQLite error_logs & /api/radar
        errors = []
        for rep in replacements:
            errors.append({
                "category": rep.get("category", "Sonstiges"),
                "error_text": rep.get("wrong", ""),
                "correction_text": rep.get("right", ""),
                "explanation": rep.get("why", ""),
            })

        return {
            "original_text": clean_text,
            "corrected_text": corrected_text,
            "level": target_level,
            "arabic_meaning": arabic_meaning,
            "is_correct": is_correct,
            "summary_ar": summary_ar,
            "explanation": summary_ar,  # Backward compatibility
            "replacements": replacements,
            "radar_rules": radar_rules,
            "diff_data": diff_data,
            "arabic_translations": arabic_translations,
            "contextual_examples": contextual_examples,
            "errors": errors,
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
