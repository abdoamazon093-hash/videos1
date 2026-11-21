import json
import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings
from app.models import CorrectionResponse, ReplacementItem, RadarRule, AiQuestionResponse, ClipExample
from app.services.corrector import run_local_corrector, extract_radar_rules, INSTANT_WORD_ARABIC_DICT

logger = logging.getLogger("gemini_service")

# ذاكرة تخزين مؤقت داخلية للاستجابات المتكررة
MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

SYSTEM_PROMPT = """أنت خبير ومصحح لغوي وسياقي ألماني رفيع المستوى (مستويات B2 / C1 / C2).
المستخدم يتحدث بالمايك أو يكتب:
1. صحح أخطاء القواعد، ترتيب الأفعال (V2 في الجملة الرئيسية، ونهاية الجملة في Nebensatz)، وحالات الإعراب (Dativ / Akkusativ)، والمتلازمات اللفظية والضمائر.
2. إذا تكلم بعبارة عربية عفوية (مثل اشرب شويه)، ترجمها لسياق ألماني طبيعي (مثل Ich trinke kurz etwas).
3. لا تعتبر الحروف الكبيرة (Großschreibung) أو علامات الترقيم أخطاءً، بل اضبطها بهدوء.
4. اذكر سبب التعديل في نقاط مختصرة جداً (5 إلى 8 كلمات لكل تعديل).
أرجع الناتج بصيغة JSON فقط بهذا الشكل:
{
  "de": "الجملة الألمانية المصححة السليمة",
  "ar": "الترجمة العربية الواضحة",
  "why": "ملخص شامل ومختصر جداً في سطر واحد لما تم تعديله",
  "rep": [
    {"w": "الكلمة أو العبارة الخطأ من كلام المستخدم", "r": "الصواب بالألماني", "why": "سبب مختصر جداً"}
  ]
}"""

async def call_gemini_correction(text: str) -> Optional[Dict[str, Any]]:
    if not settings.GEMINI_API_KEY:
        return None

    # استخدام gemini-flash-lite-latest لسرعة الرد ودقة الفلاش
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_json)
    except Exception as e:
        logger.warning(f"Gemini API request failed: {e}")
        return None
    return None

async def correct_sentence(text: str, is_final: bool = False) -> CorrectionResponse:
    clean_text = text.strip()
    cache_key = clean_text.lower()

    if cache_key in MEMORY_CACHE:
        cached = MEMORY_CACHE[cache_key]
        return CorrectionResponse(**cached)

    # 1. تجربة الذكاء الاصطناعي إذا كان المفتاح متوفراً
    ai_result = await call_gemini_correction(clean_text)

    if ai_result and "de" in ai_result:
        corrected_de = ai_result.get("de", clean_text)
        arabic_tr = ai_result.get("ar", "")
        why_sum = ai_result.get("why", "تم التدقيق السياقي والنحوي بنجاح.")
        raw_reps = ai_result.get("rep", [])

        reps = [
            ReplacementItem(
                wrong_or_arabic=r.get("w", ""),
                right_german=r.get("r", ""),
                why_replaced=r.get("why", "تصحيح سياقي ونحوي."),
                example=corrected_de
            ) for r in raw_reps if r.get("w") and r.get("r")
        ]

        radar = extract_radar_rules(corrected_de)
        is_corr = len(reps) == 0

        res_dict = {
            "user_sentence": clean_text,
            "is_correct": is_corr,
            "corrected_german": corrected_de,
            "arabic_meaning": arabic_tr,
            "why_summary": why_sum,
            "replaced_words": [r.model_dump() for r in reps],
            "radar_rules": [r.model_dump() for r in radar],
            "source": "gemini"
        }
        MEMORY_CACHE[cache_key] = res_dict
        return CorrectionResponse(**res_dict)

    # 2. خطة الطوارئ المحلية (Local Corrector Engine) في حال غياب المفتاح أو بطء الشبكة
    local_de, local_reps = run_local_corrector(clean_text)
    radar = extract_radar_rules(local_de)
    is_corr = len(local_reps) == 0

    # محاولة الحصول على ترجمة عربية بسيطة للكلمات المعروفة
    ar_meaning = "تم التصحيح بالقواعد القياسية الألمانية (محلياً) ✓"
    single_word = clean_text.lower()
    if single_word in INSTANT_WORD_ARABIC_DICT:
        ar_meaning = INSTANT_WORD_ARABIC_DICT[single_word]

    why_sum = "السياق والقواعد مضبوطة ١٠٠٪ ✓" if is_corr else " • ".join([f"{r.right_german}: {r.why_replaced}" for r in local_reps[:3]])

    res_dict = {
        "user_sentence": clean_text,
        "is_correct": is_corr,
        "corrected_german": local_de,
        "arabic_meaning": ar_meaning,
        "why_summary": why_sum,
        "replaced_words": [r.model_dump() for r in local_reps],
        "radar_rules": [r.model_dump() for r in radar],
        "source": "local_engine"
    }
    MEMORY_CACHE[cache_key] = res_dict
    return CorrectionResponse(**res_dict)

async def answer_ai_question(question: str, current_sentence: str = "") -> AiQuestionResponse:
    q_low = question.lower().strip()

    # أسئلة شائعة يتم الرد عليها فورياً
    if "zufrieden" in q_low:
        return AiQuestionResponse(
            answer_ar="• (zufrieden): صفة للعاقل فقط بمعنى «شخص راضٍ» (Ich bin zufrieden).\n• (zufriedenstellend): صفة لغير العاقل بمعنى «مُرضٍ / مقبول» وتوصف بها النتائج أو العمل (Die Ergebnisse sind zufriedenstellend).",
            german_highlight="Die Ergebnisse waren leider nicht zufriedenstellend, deshalb bin ich nicht zufrieden.",
            examples=[
                ClipExample(de="Ich bin mit meiner Arbeit zufrieden.", ar="أنا راضٍ عن عملي (عاقل)."),
                ClipExample(de="Die Ergebnisse waren nicht zufriedenstellend.", ar="النتائج لم تكن مُرضية (غير عاقل).")
            ]
        )

    if "wenn" in q_low and "als" in q_low:
        return AiQuestionResponse(
            answer_ar="• (wenn): للحدث المتكرر (مع immer/oft) أو في المضارع والمستقبل.\n• (als): لحدث وقع مرة واحدة فقط وانتهى في الماضي.",
            german_highlight="Immer wenn ich vor meinem Computer sitze, werde ich müde.",
            examples=[
                ClipExample(de="Wenn ich Zeit habe, rufe ich dich an.", ar="عندما يكون لدي وقت، سأتصل بك."),
                ClipExample(de="Als ich gestern zu Hause war, hat es geregnet.", ar="عندما كنت أمس في البيت، أمطرت (مرة واحدة).")
            ]
        )

    # إذا كان هناك مفتاح Gemini API
    if settings.GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={settings.GEMINI_API_KEY}"
        sys_prompt = f"""أنت مساعد لغة ألمانية سريع ومختصر (B2/C1). الجملة الحالية للمستخدم: "{current_sentence}".
أجب باختصار شديد ومباشر (نقطتان تبدآن بـ • بدون أي مقدمات).
أرجع JSON فقط:
{{"answer_ar": "• نقطة ١\\n• نقطة ٢", "german_highlight": "جملة ألمانية مميزة", "examples": [{{"de": "مثال", "ar": "ترجمته"}}]}}"""

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(url, json={
                    "contents": [{"role": "user", "parts": [{"text": question}]}],
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
                })
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
                    return AiQuestionResponse(
                        answer_ar=parsed.get("answer_ar", "تمت الإجابة باختصار."),
                        german_highlight=parsed.get("german_highlight", ""),
                        examples=[ClipExample(de=x["de"], ar=x["ar"]) for x in parsed.get("examples", [])]
                    )
        except Exception:
            pass

    return AiQuestionResponse(
        answer_ar="• تم تسجيل سؤالك، والصياغة الألمانية النموذجية متاحة في محرك القواعد B2/C1.",
        german_highlight=current_sentence or "Ich möchte Deutsch lernen.",
        examples=[ClipExample(de="Wir sprechen über die Grammatik.", ar="نتحدث عن القواعد النحوية.")]
    )
