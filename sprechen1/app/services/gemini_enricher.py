import json
import logging
import re
from typing import List, Dict, Any
import httpx
from app.config import GEMINI_API_KEY
from app.services.extractor import clean_for_tts, clean_for_youglish

logger = logging.getLogger(__name__)

import json
import logging
import re
from typing import List, Dict, Any
import httpx
from app.config import GEMINI_API_KEY
from app.services.extractor import clean_for_tts, clean_for_youglish

logger = logging.getLogger(__name__)

# Primary and fallback Gemini models
GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash"
]

# Comprehensive offline dictionary fallback for common B1/B2 verbs & vocabulary
OFFLINE_GERMAN_ARABIC_DICT: Dict[str, Dict[str, str]] = {
    "abnehmen": {"ar": "يأخذ من شخص / ينقص / يخفّض الوزن / يستلم", "perf": "hat abgenommen", "praet": "nahm ab"},
    "abtrocknen": {"ar": "يجفف / يمسح بالمنشفة", "perf": "hat abgetrocknet", "praet": "trocknete ab"},
    "anbieten": {"ar": "يعرض / يقدم", "perf": "hat angeboten", "praet": "bot an"},
    "annehmen": {"ar": "يقبل / يفترض / يستلم", "perf": "hat angenommen", "praet": "nahm an"},
    "anrufen": {"ar": "يتصل هاتفياً", "perf": "hat angerufen", "praet": "rief an"},
    "anschauen": {"ar": "يشاهد / ينظر إلى", "perf": "hat angeschaut", "praet": "schaute an"},
    "ansehen": {"ar": "ينظر إلى / يشاهد / يعتبر", "perf": "hat angesehen", "praet": "sah an"},
    "anstrengen": {"ar": "يُجهد / يتعب", "perf": "hat angestrengt", "praet": "strengte an"},
    "antworten": {"ar": "يجيب / يردّ على", "perf": "hat geantwortet", "praet": "antwortete"},
    "anvertrauen": {"ar": "يأتمن على / يودع سراً", "perf": "hat anvertraut", "praet": "vertraute an"},
    "anziehen": {"ar": "يرتدي / يلبس / يجذب", "perf": "hat angezogen", "praet": "zog an"},
    "anzünden": {"ar": "يشعل / يوقد (شمعة أو ناراً)", "perf": "hat angezündet", "praet": "zündete an"},
    "auffallen": {"ar": "يلفت الانتباه / يثير الملاحظة", "perf": "ist aufgefallen", "praet": "fiel auf"},
    "aufgeben": {"ar": "يستسلم / يتخلى عن / يرسل طرداً", "perf": "hat aufgegeben", "praet": "gab auf"},
    "aufheben": {"ar": "يرفع من الأرض / يحفظ / يلغي", "perf": "hat aufgehoben", "praet": "hob auf"},
    "aufmachen": {"ar": "يفتح (باباً أو نافذة)", "perf": "hat aufgemacht", "praet": "machte auf"},
    "aufnehmen": {"ar": "يستقبل / يسجل / يلتقط صورة", "perf": "hat aufgenommen", "praet": "nahm auf"},
    "aufräumen": {"ar": "يرتب / ينظم المكان", "perf": "hat aufgeräumt", "praet": "räumte auf"},
    "ausgeben": {"ar": "ينفق (مالاً) / يصدر", "perf": "hat ausgegeben", "praet": "gab aus"},
    "auspacken": {"ar": "يفرغ الحقائب / يفتح طرداً", "perf": "hat ausgepackt", "praet": "packte aus"},
    "ausschalten": {"ar": "يطفئ / يوقف تشغيل جهاز", "perf": "hat ausgeschaltet", "praet": "schaltete aus"},
    "aussprechen": {"ar": "ينطق / يعبّر عن / يلفظ", "perf": "hat ausgesprochen", "praet": "sprach aus"},
    "aussuchen": {"ar": "يختار / ينتقي", "perf": "hat ausgesucht", "praet": "suchte aus"},
    "ausweichen": {"ar": "يتفادى / يتجنب / يفسح الطريق", "perf": "ist ausgewichen", "praet": "wich aus"},
    "ausziehen": {"ar": "يخلع ملابسه / يغادر السكن", "perf": "hat/ist ausgezogen", "praet": "zog aus"},
    "backen": {"ar": "يخبز", "perf": "hat gebacken", "praet": "backte/buk"},
    "baden": {"ar": "يستحم / يسبح", "perf": "hat gebadet", "praet": "badete"},
    "bauen": {"ar": "يبني / يشيد", "perf": "hat gebaut", "praet": "baute"},
    "beachten": {"ar": "يراعي / ينتبه إلى / يلتزم بـ", "perf": "hat beachtet", "praet": "beachtete"},
    "beantragen": {"ar": "يتقدم بطلب رسمي", "perf": "hat beantragt", "praet": "beantragte"},
    "beantworten": {"ar": "يجيب على (سؤال أو رسالة)", "perf": "hat beantwortet", "praet": "beantwortete"},
    "bedienen": {"ar": "يشغل آلة / يخدم زبوناً", "perf": "hat bedient", "praet": "bediente"},
    "begegnen": {"ar": "يقابل صدفة / يصادف", "perf": "ist begegnet", "praet": "begegnete"},
    "beginnen": {"ar": "يبدأ / يشرع في", "perf": "hat begonnen", "praet": "begann"},
    "begründen": {"ar": "يعلل / يبرر / يعطي أسباباً", "perf": "hat begründet", "praet": "begründete"},
    "begrüßen": {"ar": "يرحب بـ / يحيي", "perf": "hat begrüßt", "praet": "begrüßte"},
    "behalten": {"ar": "يحتفظ بـ / يبقي عنده", "perf": "hat behalten", "praet": "behielt"},
    "bekommen": {"ar": "يحصل على / ينال", "perf": "hat bekommen", "praet": "bekam"},
    "bemerken": {"ar": "يلاحظ / يدرك / يبدي ملاحظة", "perf": "hat bemerkt", "praet": "bemerkte"},
    "benachrichtigen": {"ar": "يبلغ / يخطر رسمياً", "perf": "hat benachrichtigt", "praet": "benachrichtigte"},
    "benutzen": {"ar": "يستخدم / يستعمل", "perf": "hat benutzt", "praet": "benutzte"},
    "benützen": {"ar": "يستخدم / يستعمل", "perf": "hat benützt", "praet": "benützte"},
    "beraten": {"ar": "ينصح / يقدم مشورة / يتشاور", "perf": "hat beraten", "praet": "beriet"},
    "berücksichtigen": {"ar": "يأخذ بالاعتبار / يراعي", "perf": "hat berücksichtigt", "praet": "berücksichtigte"},
    "beruhigen": {"ar": "يهدئ / يطمئن", "perf": "hat beruhigt", "praet": "beruhigte"},
    "beschreiben": {"ar": "يصف / يصور بالكلمات", "perf": "hat beschrieben", "praet": "beschrieb"},
    "besichtigen": {"ar": "يزور معالم / يعاين موقعاً", "perf": "hat besichtigt", "praet": "besichtigte"},
    "besitzen": {"ar": "يمتلك / يحوز", "perf": "hat besessen", "praet": "besaß"},
    "bestellen": {"ar": "يطلب (بضاعة أو طعاماً) / يزرع", "perf": "hat bestellt", "praet": "bestellte"},
    "bestimmen": {"ar": "يحدد / يقرر / يعيّن", "perf": "hat bestimmt", "praet": "bestimmte"},
    "besuchen": {"ar": "يزور شخصاً أو مكاناً", "perf": "hat besucht", "praet": "besuchte"},
    "betrügen": {"ar": "يخدع / يغش / يخون", "perf": "hat betrogen", "praet": "betrog"},
    "beweisen": {"ar": "يثبت / يبرهن على", "perf": "hat bewiesen", "praet": "bewies"},
    "bezahlen": {"ar": "يدفع مالاً / يسدد حساباً", "perf": "hat bezahlt", "praet": "bezahlte"},
    "bieten": {"ar": "يقدم / يعرض / يتيح فرصة", "perf": "hat geboten", "praet": "bot"},
    "borgen": {"ar": "يستعير / يقرض", "perf": "hat geborgt", "praet": "borgte"},
    "brauchen": {"ar": "يحتاج إلى / يتطلب", "perf": "hat gebraucht", "praet": "brauchte"},
    "bringen": {"ar": "يحضر / يجلب / يوصل", "perf": "hat gebracht", "praet": "brachte"},
    "danken": {"ar": "يشكر", "perf": "hat gedankt", "praet": "dankte"},
    "dienen": {"ar": "يخدم / يفيد", "perf": "hat gedient", "praet": "diente"},
    "drehen": {"ar": "يدير / يلف / يصوّر فيلماً", "perf": "hat gedreht", "praet": "drehte"},
    "drohen": {"ar": "يهدد", "perf": "hat gedroht", "praet": "drohte"},
    "drücken": {"ar": "يضغط / يعصر / يطبع", "perf": "hat gedrückt", "praet": "drückte"},
    "drucken": {"ar": "يطبع ورقياً", "perf": "hat gedruckt", "praet": "druckte"},
    "ehren": {"ar": "يكرّم / يشرّف / يحترم", "perf": "hat geehrt", "praet": "ehrte"},
    "einfallen": {"ar": "يخطر على البال / يتذكر فجأة", "perf": "ist eingefallen", "praet": "fiel ein"},
    "einkaufen": {"ar": "يتسوق / يشتري حاجيات", "perf": "hat eingekauft", "praet": "kaufte ein"},
    "einladen": {"ar": "يدعو / يعزم شخصاً", "perf": "hat eingeladen", "praet": "lud ein"},
    "einpacken": {"ar": "يحزم الأمتعة / يغلّف هدية", "perf": "hat eingepackt", "praet": "packte ein"},
    "empfehlen": {"ar": "يوصي بـ / يزكّي / ينصح بـ", "perf": "hat empfohlen", "praet": "empfahl"},
    "enthalten": {"ar": "يحتوي على / يتضمن", "perf": "hat enthalten", "praet": "enthielt"},
    "entlassen": {"ar": "يقيل من العمل / يصرّف / يسرّح", "perf": "hat entlassen", "praet": "entließ"},
    "erfahren": {"ar": "يعلم / يكتشف خبراً / يمر بتجربة", "perf": "hat erfahren", "praet": "erfuhr"},
    "erfinden": {"ar": "يخترع / يبتكر", "perf": "hat erfunden", "praet": "erfand"},
    "erfüllen": {"ar": "يحقق أملاً / يفي بوعد", "perf": "hat erfüllt", "praet": "erfüllte"},
    "erhalten": {"ar": "يتلقى / يستلم / يحافظ على", "perf": "hat erhalten", "praet": "erhielt"},
    "erhöhen": {"ar": "يرفع / يزيد (الأسعار أو الأجور)", "perf": "hat erhöht", "praet": "erhöhte"},
    "erkennen": {"ar": "يتعرف على / يدرك حقيقة", "perf": "hat erkannt", "praet": "erkannte"},
    "erklären": {"ar": "يشرح / يوضح / يعلن", "perf": "hat erklärt", "praet": "erklärte"},
    "erlauben": {"ar": "يسمح بـ / يأذن", "perf": "hat erlaubt", "praet": "erlaubte"},
    "erledigen": {"ar": "ينجز مهمة / يقضي أمراً", "perf": "hat erledigt", "praet": "erledigte"},
    "eröffnen": {"ar": "يفتتح (حساباً أو مشروعاً)", "perf": "hat eröffnet", "praet": "eröffnete"},
    "erreichen": {"ar": "يصل إلى / يحقق هدفاً / يتواصل مع", "perf": "hat erreicht", "praet": "erreichte"},
    "erschrecken": {"ar": "يفزع / يرعب / يخيف", "perf": "hat/ist erschreckt/erschrocken", "praet": "erschrak"},
    "erwarten": {"ar": "ينتظر / يتوقع", "perf": "hat erwartet", "praet": "erwartete"},
    "erzählen": {"ar": "يروي / يحكي قصة", "perf": "hat erzählt", "praet": "erzählte"},
    "erziehen": {"ar": "يربي / ينشئ طفلاً", "perf": "hat erzogen", "praet": "erzog"},
    "essen": {"ar": "يأكل", "perf": "hat gegessen", "praet": "aß"},
    "fehlen": {"ar": "ينقص / يغيب / يفتقد", "perf": "hat gefehlt", "praet": "fehlte"},
    "feiern": {"ar": "يحتفل بـ", "perf": "hat gefeiert", "praet": "feierte"},
    "finden": {"ar": "يجد / يعثر على / يعتبر", "perf": "hat gefunden", "praet": "fand"},
    "folgen": {"ar": "يتبع / يلحق بـ / يقتدي", "perf": "ist gefolgt", "praet": "folgte"},
    "fordern": {"ar": "يطالب بـ / يستلزم", "perf": "hat gefordert", "praet": "forderte"},
    "fördern": {"ar": "يدعم / يشجع / يستخرج ثروة", "perf": "hat gefördert", "praet": "förderte"},
    "fotografieren": {"ar": "يلتقط صوراً / يصور", "perf": "hat fotografiert", "praet": "fotografierte"},
    "fragen": {"ar": "يسأل / يستفسر", "perf": "hat gefragt", "praet": "fragte"},
    "frühstücken": {"ar": "يتناول طعام الإفطار", "perf": "hat gefrühstückt", "praet": "frühstückte"},
    "fühlen": {"ar": "يشعر بـ / يحس", "perf": "hat gefühlt", "praet": "fühlte"},
    "führen": {"ar": "يقود / يدير / يرشد", "perf": "hat geführt", "praet": "führte"},
    "geben": {"ar": "يعطي / يمنح / يسلّم", "perf": "hat gegeben", "praet": "gab"},
    "gefallen": {"ar": "يعجب / يروق لـ", "perf": "hat gefallen", "praet": "gefiel"},
    "gehorchen": {"ar": "يطيع / يمتثل للأمر", "perf": "hat gehorcht", "praet": "gehorchte"},
    "gehören": {"ar": "ينتمي إلى / يخص شخصاً", "perf": "hat gehört", "praet": "gehörte"},
    "gelingen": {"ar": "ينجح في / يوفق", "perf": "ist gelungen", "praet": "gelang"},
    "genügen": {"ar": "يكفي / يفي بالغرض", "perf": "hat genügt", "praet": "genügte"},
    "geschehen": {"ar": "يحدث / يقع / يطرأ", "perf": "ist geschehen", "praet": "geschah"},
    "glauben": {"ar": "يصدق / يؤمن بـ / يعتقد", "perf": "hat geglaubt", "praet": "glaubte"},
    "gratulieren": {"ar": "يهنئ بمناسبة", "perf": "hat gratuliert", "praet": "gratulierte"},
    "grüßen": {"ar": "يسلّم على / يحيي", "perf": "hat gegrüßt", "praet": "grüßte"},
    "haben": {"ar": "يملك / لديه", "perf": "hat gehabt", "praet": "hatte"},
    "hassen": {"ar": "يكره / يمقت", "perf": "hat gehasst", "praet": "hasste"},
    "heben": {"ar": "يرفع / يحمل للأعلى", "perf": "hat gehoben", "praet": "hob"},
    "heizen": {"ar": "يدفئ / يسخن", "perf": "hat geheizt", "praet": "heizte"},
    "helfen": {"ar": "يساعد / يعين", "perf": "hat geholfen", "praet": "half"},
    "herstellen": {"ar": "ينتج / يصنع / يركّب", "perf": "hat hergestellt", "praet": "stellte her"},
    "holen": {"ar": "يحضر / يجلب / يستدعي", "perf": "hat geholt", "praet": "holte"},
    "hören": {"ar": "يسمع / يستمع إلى", "perf": "hat gehört", "praet": "hörte"},
    "informieren": {"ar": "يبلغ / يخبر / يطّلع", "perf": "hat informiert", "praet": "informierte"},
    "kaufen": {"ar": "يشتري", "perf": "hat gekauft", "praet": "kaufte"},
    "kennen": {"ar": "يعرف شخصاً أو مكاناً", "perf": "hat gekannt", "praet": "kannte"},
    "kochen": {"ar": "يطبخ / يغلي", "perf": "hat gekocht", "praet": "kochte"},
    "kontrollieren": {"ar": "يراقب / يفتش / يراجع", "perf": "hat kontrolliert", "praet": "kontrollierte"},
    "korrigieren": {"ar": "يصحح / يصوب خطأ", "perf": "hat korrigiert", "praet": "korrigierte"},
    "kündigen": {"ar": "يفسخ عقداً / يستقيل / يفصل من العمل", "perf": "hat gekündigt", "praet": "kündigte"},
    "küssen": {"ar": "يقبّل", "perf": "hat geküsst", "praet": "küsste"},
    "lassen": {"ar": "يترك / يسمح / يدع", "perf": "hat gelassen", "praet": "ließ"},
    "leid tun": {"ar": "يؤسف / يحزن", "perf": "hat leidgetan", "praet": "tat leid"},
    "leihen": {"ar": "يقرض / يستعير", "perf": "hat geliehen", "praet": "lieh"},
    "leiten": {"ar": "يقود / يدير / يوجه", "perf": "hat geleitet", "praet": "leitete"},
    "lernen": {"ar": "يتعلم / يدرس", "perf": "hat gelernt", "praet": "lernte"},
    "lesen": {"ar": "يقرأ", "perf": "hat gelesen", "praet": "las"},
    "lieben": {"ar": "يحب / يعشق", "perf": "hat geliebt", "praet": "liebte"},
    "liefern": {"ar": "يوصل طلباً / يسلّم بضاعة", "perf": "hat geliefert", "praet": "lieferte"},
    "loben": {"ar": "يمدح / يثني على", "perf": "hat gelobt", "praet": "lobte"},
    "lösen": {"ar": "يحل مسألة / يفك / يذيب", "perf": "hat gelöst", "praet": "löste"},
    "machen": {"ar": "يفعل / يصنع / يقوم بـ", "perf": "hat gemacht", "praet": "machte"},
    "malen": {"ar": "يرسم بالألوان / يدهن", "perf": "hat gemalt", "praet": "malte"},
    "markieren": {"ar": "يعلّم / يظلل نصاً / يحدد", "perf": "hat markiert", "praet": "markierte"},
    "meinen": {"ar": "يقصد / يعتقد / يرى رأياً", "perf": "hat gemeint", "praet": "meinte"},
    "melden": {"ar": "يبلّغ / يسجل حضوراً", "perf": "hat gemeldet", "praet": "meldete"},
    "merken": {"ar": "يتذكر / يحفظ في الذاكرة / يلاحظ", "perf": "hat gemerkt", "praet": "merkte"},
    "messen": {"ar": "يقيس (الحجم أو المسافة)", "perf": "hat gemessen", "praet": "maß"},
    "mieten": {"ar": "يستأجر", "perf": "hat gemietet", "praet": "mietete"},
    "mitbringen": {"ar": "يحضر معه / يصحب معه", "perf": "hat mitgebracht", "praet": "brachte mit"},
    "mitteilen": {"ar": "يبلغ / يعلم خبراً", "perf": "hat mitgeteilt", "praet": "teilte mit"},
    "nachgehen": {"ar": "يتقصى / يتابع أثراً / يدقق", "perf": "ist nachgegangen", "praet": "ging nach"},
    "nehmen": {"ar": "يأخذ / يتناول", "perf": "hat genommen", "praet": "nahm"},
    "nennen": {"ar": "يسمي / يذكر اسماً", "perf": "hat genannt", "praet": "nannte"},
    "nutzen": {"ar": "يستفيد من / يستغل فرصة", "perf": "hat genutzt", "praet": "nutzte"},
    "nützen": {"ar": "ينفع / يجدي نفعاً", "perf": "hat genützt", "praet": "nützte"},
    "passen": {"ar": "يناسب / يلائم في المقاس", "perf": "hat gepasst", "praet": "passte"},
    "pflegen": {"ar": "يعتني بـ / يرعى مريضاً", "perf": "hat gepflegt", "praet": "pflegte"},
    "prüfen": {"ar": "يفحص / يختبر / يدقق", "perf": "hat geprüft", "praet": "prüfte"},
    "putzen": {"ar": "ينظف (الأسنان أو النوافذ)", "perf": "hat geputzt", "praet": "putzte"},
    "raten": {"ar": "ينصح / يحزر لغزاً", "perf": "hat geraten", "praet": "riet"},
    "rauchen": {"ar": "يدخن", "perf": "hat geraucht", "praet": "rauchte"},
    "reichen": {"ar": "يناول / يكفي / يمتد إلى", "perf": "hat gereicht", "praet": "reichte"},
    "reparieren": {"ar": "يصلح عطلاً", "perf": "hat repariert", "praet": "reparierte"},
    "reservieren": {"ar": "يحجز مقعداً أو غرفة", "perf": "hat reserviert", "praet": "reservierte"},
    "riechen": {"ar": "يشم / تنبعث منه رائحة", "perf": "hat gerochen", "praet": "roch"},
    "sammeln": {"ar": "يجمع / يحوش", "perf": "hat gesammelt", "praet": "sammelte"},
    "schaden": {"ar": "يضر / يؤذي", "perf": "hat geschadet", "praet": "schadete"},
    "schenken": {"ar": "يهدي / يمنح هدية", "perf": "hat geschenkt", "praet": "schenkte"},
    "schlagen": {"ar": "يضرب / يهزم في منافسة", "perf": "hat geschlagen", "praet": "schlug"},
    "schließen": {"ar": "يغلق (باباً أو حساباً) / يستنتج", "perf": "hat geschlossen", "praet": "schloss"},
    "schmecken": {"ar": "يتذوق / يكون طعمه لذيذاً", "perf": "hat geschmeckt", "praet": "schmeckte"},
    "schneiden": {"ar": "يقص / يجرح / يقطع", "perf": "hat geschnitten", "praet": "schnitt"},
    "schreiben": {"ar": "يكتب / يدون", "perf": "hat geschrieben", "praet": "schrieb"},
    "schulden": {"ar": "يدين بمال / يكون مديناً", "perf": "hat geschuldet", "praet": "schuldete"},
    "sehen": {"ar": "يرى / يشاهد", "perf": "hat gesehen", "praet": "sah"},
    "senden": {"ar": "يرسل / يبث برنامجاً", "perf": "hat gesendet/gesandt", "praet": "sendete/sandte"},
    "sparen": {"ar": "يدخر مالاً / يوفّر جهداً", "perf": "hat gespart", "praet": "sparte"},
    "spielen": {"ar": "يلعب / يعزف موسيقى / يمثل دوراً", "perf": "hat gespielt", "praet": "spielte"},
    "spülen": {"ar": "يغسل الأطباق / يشطف بالماء", "perf": "hat gespült", "praet": "spülte"},
    "starten": {"ar": "يبدأ / يقلع / يشغل محركاً", "perf": "ist/hat gestartet", "praet": "startete"},
    "stehlen": {"ar": "يسرق", "perf": "hat gestohlen", "praet": "stahl"},
    "stoppen": {"ar": "يوقف / يفرمل", "perf": "hat gestoppt", "praet": "stoppte"},
    "stören": {"ar": "يزعج / يعيق", "perf": "hat gestört", "praet": "störte"},
    "studieren": {"ar": "يدرس في الجامعة / يبحث بتعمق", "perf": "hat studiert", "praet": "studierte"},
    "suchen": {"ar": "يبحث عن / يفتش", "perf": "hat gesucht", "praet": "suchte"},
    "tanzen": {"ar": "يرقص", "perf": "hat getanzt", "praet": "tanzte"},
    "teilen": {"ar": "يقسم / يشارك (منشوراً أو طعاماً)", "perf": "hat geteilt", "praet": "teilte"},
    "töten": {"ar": "يقتل / ينهي حياة", "perf": "hat getötet", "praet": "tötete"},
    "tragen": {"ar": "يرتدي / يحمل ثقلاً / يتحمل مسؤولية", "perf": "hat getragen", "praet": "trug"},
    "transportieren": {"ar": "ينقل بضائع أو أثاثاً", "perf": "hat transportiert", "praet": "transportierte"},
    "treffen": {"ar": "يلتقي بـ / يصيب الهدف", "perf": "hat getroffen", "praet": "traf"},
    "trinken": {"ar": "يشرب", "perf": "hat getrunken", "praet": "trank"},
    "trocknen": {"ar": "يجف / ينشف", "perf": "hat/ist getrocknet", "praet": "trocknete"},
    "überfahren": {"ar": "يدهس بسيارة / يقطع إشارة", "perf": "hat überfahren", "praet": "überfuhr"},
    "überholen": {"ar": "يتجاوز سيارة / يتخطى منافساً", "perf": "hat überholt", "praet": "überholte"},
    "übernehmen": {"ar": "يتولى إدارة / يتحمل مسؤولية", "perf": "hat übernommen", "praet": "übernahm"},
    "überqueren": {"ar": "يعبر الشارع أو الجسر", "perf": "hat überquert", "praet": "überquerte"},
    "überraschen": {"ar": "يفاجئ / يباغت", "perf": "hat überrascht", "praet": "überraschte"},
    "überreden": {"ar": "يقنع شخصاً بالكلام / يحثّه", "perf": "hat überredet", "praet": "überredete"},
    "übersetzen": {"ar": "يترجم لغة / يعبر إلى الضفة", "perf": "hat übersetzt", "praet": "übersetzte"},
    "überweisen": {"ar": "يحوّل مالاً مصرفياً / يحيل إلى طبيب", "perf": "hat überwiesen", "praet": "überwies"},
    "überzeugen": {"ar": "يقنع بالحجة والدليل", "perf": "hat überzeugt", "praet": "überzeugte"},
    "umtauschen": {"ar": "يستبدل بضاعة / يصرّف عملة", "perf": "hat umgetauscht", "praet": "tauschte um"},
    "unterrichten": {"ar": "يدرّس / يعلّم", "perf": "hat unterrichtet", "praet": "unterrichtete"},
    "unterschreiben": {"ar": "يوقع / يمضي على عقد", "perf": "hat unterschrieben", "praet": "unterschrieb"},
    "unterstützen": {"ar": "يدعم / يساند مادياً أو معنوياً", "perf": "hat unterstützt", "praet": "unterstützte"},
    "untersuchen": {"ar": "يفحص طبياً / يحقق في قضية", "perf": "hat untersucht", "praet": "untersuchte"},
    "verändern": {"ar": "يغيّر / يبدّل", "perf": "hat verändert", "praet": "veränderte"},
    "verbieten": {"ar": "يمنع / يحظر رسمياً", "perf": "hat verboten", "praet": "verbot"},
    "verbrauchen": {"ar": "يستهلك (طاقة أو وقوداً)", "perf": "hat verbraucht", "praet": "verbrauchte"},
    "verdächtigen": {"ar": "يشتبه في / يتهم", "perf": "hat verdächtigt", "praet": "verdächtigte"},
    "verdienen": {"ar": "يكسب مالاً بالعمل / يستحق تقديراً", "perf": "hat verdient", "praet": "verdiente"},
    "vergessen": {"ar": "ينسى", "perf": "hat vergessen", "praet": "vergaß"},
    "vergleichen": {"ar": "يقارن بين أمرين", "perf": "hat verglichen", "praet": "verglich"},
    "vergrößern": {"ar": "يكبّر / يوسّع نطاقاً", "perf": "hat vergrößert", "praet": "vergrößerte"},
    "verhaften": {"ar": "يقبض على / يعتقل", "perf": "hat verhaftet", "praet": "verhaftete"},
    "verheimlichen": {"ar": "يخفي / يكتم سراً", "perf": "hat verheimlicht", "praet": "verheimlichte"},
    "verhindern": {"ar": "يمنع وقوع أمر / يعرقل", "perf": "hat verhindert", "praet": "verhinderte"},
    "verkaufen": {"ar": "يبيع", "perf": "hat verkauft", "praet": "verkaufte"},
    "verlängern": {"ar": "يمدد مدة / يطيل إقامة أو عقداً", "perf": "hat verlängert", "praet": "verlängerte"},
    "verlassen": {"ar": "يغادر مكاناً / يهجر شخصاً", "perf": "hat verlassen", "praet": "verließ"},
    "verlieren": {"ar": "يفقد / يخسر شيئاً أو مباراة", "perf": "hat verloren", "praet": "verlor"},
    "vermieten": {"ar": "يؤجر لآخرين", "perf": "hat vermietet", "praet": "vermietete"},
    "verpassen": {"ar": "يفوّت قطاراً أو موعداً", "perf": "hat verpasst", "praet": "verpasste"},
    "verraten": {"ar": "يفشي سراً / يخون وطناً", "perf": "hat verraten", "praet": "verriet"},
    "verschreiben": {"ar": "يصف دواءً طبياً / يخطئ في الكتابة", "perf": "hat verschrieben", "praet": "verschrieb"},
    "verschweigen": {"ar": "يسكت عن / يكتم أمراً", "perf": "hat verschwiegen", "praet": "verschwieg"},
    "versichern": {"ar": "يؤمّن على شيء / يؤكد ويضمن", "perf": "hat versichert", "praet": "versicherte"},
    "versprechen": {"ar": "يعد بـ / يقطع وعداً", "perf": "hat versprochen", "praet": "versprach"},
    "verstecken": {"ar": "يخبئ / يخفي", "perf": "hat versteckt", "praet": "versteckte"},
    "verstehen": {"ar": "يفهم / يستوعب", "perf": "hat verstanden", "praet": "verstand"},
    "verteilen": {"ar": "يوزع على الناس", "perf": "hat verteilt", "praet": "verteilte"},
    "vertrauen": {"ar": "يثق في شخص", "perf": "hat vertraut", "praet": "vertraute"},
    "vertreten": {"ar": "ينوب عن / يمثل جهة", "perf": "hat vertreten", "praet": "vertrat"},
    "verursachen": {"ar": "يتسبب في حادث أو ضرر", "perf": "hat verursacht", "praet": "verursachte"},
    "verwenden": {"ar": "يستخدم / يوظف وسيلة", "perf": "hat verwendet", "praet": "verwendete"},
    "verzeihen": {"ar": "يسامح / يغفر لشخص", "perf": "hat verziehen", "praet": "verzieh"},
    "vorbereiten": {"ar": "يجهز / يعدّ لامتحان أو رحلة", "perf": "hat vorbereitet", "praet": "bereitete vor"},
    "vorlesen": {"ar": "يقرأ بصوت عالٍ للآخرين", "perf": "hat vorgelesen", "praet": "las vor"},
    "vorschlagen": {"ar": "يقترح فكرة أو خطة", "perf": "hat vorgeschlagen", "praet": "schlug vor"},
    "vorstellen": {"ar": "يقدم شخصاً / يتخيل فكرة", "perf": "hat vorgestellt", "praet": "stellte vor"},
    "warnen": {"ar": "يحذر من خطر", "perf": "hat gewarnt", "praet": "warnte"},
    "waschen": {"ar": "يغسل ملابس أو يدين", "perf": "hat gewaschen", "praet": "wusch"},
    "wechseln": {"ar": "يغيّر / يبدّل نقوداً أو إطارات", "perf": "hat gewechselt", "praet": "wechselte"},
    "wecken": {"ar": "يوقظ شخصاً من النوم", "perf": "hat geweckt", "praet": "weckte"},
    "weh tun": {"ar": "يؤلم / يوجع", "perf": "hat wehgetan", "praet": "tat weh"},
    "werfen": {"ar": "يرمي / يقذف شيئاً", "perf": "hat geworfen", "praet": "warf"},
    "widersprechen": {"ar": "يعارض / يناقض في الرأي", "perf": "hat widersprochen", "praet": "widersprach"},
    "wiederholen": {"ar": "يكرر / يعيد مراجعة دروس", "perf": "hat wiederholt", "praet": "wiederholte"},
    "wiegen": {"ar": "يزن بالميزان / يبلغ وزنه", "perf": "hat gewogen", "praet": "wog"},
    "winken": {"ar": "يلوح بيده مودعاً أو مرحباً", "perf": "hat gewinkt", "praet": "winkte"},
    "wissen": {"ar": "يعلم / يعرف معلومة", "perf": "hat gewusst", "praet": "wusste"},
    "wünschen": {"ar": "يتمنى / يرغب في", "perf": "hat gewünscht", "praet": "wünschte"},
    "zählen": {"ar": "يعدّ / يحصي أرقاماً", "perf": "hat gezählt", "praet": "zählte"},
    "zahlen": {"ar": "يدفع مالاً / يسدد حساباً", "perf": "hat gezahlt", "praet": "zahlte"},
    "zeichnen": {"ar": "يرسم بالقلم أو الفحم", "perf": "hat gezeichnet", "praet": "zeichnete"},
    "zeigen": {"ar": "يُري / يوضح / يشير إلى", "perf": "hat gezeigt", "praet": "zeigte"},
    "zerstören": {"ar": "يدمر / يخرّب كلياً", "perf": "hat zerstört", "praet": "zerstörte"}
}


def build_fallback_examples(word: str, spoken_word: str, arabic: str, synonym: str) -> List[Dict[str, str]]:
    """Builds standard B2 contextual examples matching the template structure."""
    w = spoken_word or word
    ar = arabic.split('/')[0].strip() if arabic else w
    syn = synonym.split(',')[0].strip() if synonym else ''

    return [
        {
            "tag": "سياق B2 تطبيقي",
            "de": f"In aktuellen Diskussionen spielt der Ausdruck „{w}“ eine wichtige Rolle{f', oft im Sinne von „{syn}“' if syn else ''}.",
            "ar": f"في النقاشات الحالية يلعب التعبير \"{w}\" ({ar}) دوراً مهماً{f'، وغالباً بمعنى \"{syn}\"' if syn else ''}."
        },
        {
            "tag": "الحياة المهنية والدراسة",
            "de": f"Im Berufsalltag und im Studium begegnet man dem Begriff „{w}“ immer häufiger.",
            "ar": f"في الحياة المهنية اليومية وفي الدراسة يصادف المرء مصطلح \"{w}\" ({ar}) بشكل متزايد."
        },
        {
            "tag": "مقال / عرض تقديمي B2",
            "de": f"Für die B2-Prüfung sollte man „{w}“ sicher im Kontext verwenden können.",
            "ar": f"من أجل امتحان B2 ينبغي للمرء أن يتمكن من استخدام \"{w}\" ({ar}) بثقة داخل السياق."
        }
    ]


def rule_based_full_check(raw_word: str) -> tuple[bool, str, str, str]:
    """
    Detects if word is likely a verb or verb phrase and retrieves or estimates
    Arabic translation, Perfekt, and Präteritum.
    Returns: (is_verb, perfekt, praeteritum, arabic)
    """
    clean_v = clean_for_tts(raw_word).lower()
    
    # Check offline dictionary first
    if clean_v in OFFLINE_GERMAN_ARABIC_DICT:
        d = OFFLINE_GERMAN_ARABIC_DICT[clean_v]
        return True, d["perf"], d["praet"], d["ar"]

    w = raw_word.strip()
    is_v = False
    perfekt = ""
    praeteritum = ""
    ar = ""

    if "/" in w or "sich " in w or any(w.endswith(e) for e in ["en", "eln", "ern"]) and not any(w.startswith(art) for art in ["der ", "die ", "das "]):
        is_v = True
        if any(mov in clean_v for mov in ["gehen", "kommen", "fallen", "brechen", "reisen", "steigen", "laufen"]):
            perfekt = f"ist {clean_v}"
        else:
            perfekt = f"hat {clean_v}"
            
    return is_v, perfekt, praeteritum, ar


def rule_based_verb_check(raw_word: str) -> tuple[bool, str]:
    """
    Backward-compatible 2-tuple check returning (is_verb, perfekt).
    """
    is_v, perf, _, _ = rule_based_full_check(raw_word)
    return is_v, perf


async def enrich_vocabulary_batch(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches a batch of vocabulary items using Gemini API or rich offline dictionary fallback.
    Guarantees:
    1. If Arabic translation is missing or empty, generates rich Arabic meanings separated by ' / '.
    2. Identifies is_verb, exact Perfekt, and exact Präteritum.
    3. Translates existing German example sentences into natural Arabic.
    """
    if not items:
        return []

    # If Gemini API Key is available, try Gemini models sequentially
    if GEMINI_API_KEY:
        prompt = """
You are an expert German-Arabic lexicographer (Goethe-Institut B2/C1 standard).
Analyze the following list of German vocabulary items.
For EACH item, return a JSON object with:
1. "word": original German word
2. "spoken_word": cleaned headword for natural German Web Speech TTS (remove cases +AKK/+DAT, parens, notes)
3. "youglish_query": headword without leading articles
4. "arabic": ACCURATE, HIGH-QUALITY ARABIC TRANSLATION. If the word has multiple common meanings, list them separated by ' / ' (e.g. 'يأخذ / ينقص / يستلم / يخفّض الوزن'). NEVER leave arabic empty.
5. "synonyms": 2 to 4 high-frequency German synonyms, comma-separated
6. "synonym_list": array of individual synonym strings
7. "is_verb": boolean (true if word is a verb)
8. "perfekt": exact Perfekt form ("hat/ist + Partizip II" e.g. "hat abgenommen", "ist aufgefallen")
9. "praeteritum": exact Präteritum form (e.g. "nahm ab", "fiel auf")
10. "examples": array of example objects:
    - If the input item already has a German example sentence in its examples, PRESERVE that German sentence in "de", and provide an accurate Arabic translation in "ar"!
    - If the input item has no examples, provide 2 realistic B2 exam level example sentences with "de" and "ar".
    - "tag": label (e.g. "مثال سياقي" or grammatical case)

Input items:
""" + json.dumps([
            {
                "word": it.get("word", ""),
                "arabic": it.get("arabic", ""),
                "synonym": it.get("synonym", ""),
                "examples": it.get("examples", [])
            } for it in items
        ], ensure_ascii=False)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }

        for model_name in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw_text)

                        results = []
                        for idx, res in enumerate(parsed):
                            orig_it = items[idx] if idx < len(items) else {}
                            orig_page = orig_it.get("page", 1)
                            raw_w = res.get("word") or orig_it.get("word", "")
                            spoken_w = res.get("spoken_word") or clean_for_tts(raw_w)
                            yg = res.get("youglish_query") or clean_for_youglish(spoken_w)

                            # Priority: Gemini Arabic -> Original Arabic -> Offline Dictionary
                            dict_info = OFFLINE_GERMAN_ARABIC_DICT.get(spoken_w.lower(), {})
                            ar = res.get("arabic") or orig_it.get("arabic") or dict_info.get("ar", "")
                            if not ar:
                                ar = dict_info.get("ar", "")

                            syn = orig_it.get("synonym") or res.get("synonyms", "")
                            syn_list = res.get("synonym_list") or [s.strip() for s in re.split(r'[/,]', syn) if s.strip()]
                            is_v = bool(orig_it.get("is_verb") or res.get("is_verb") or dict_info)
                            perf = orig_it.get("perfekt") or res.get("perfekt") or dict_info.get("perf", "")
                            praet = orig_it.get("praeteritum") or res.get("praeteritum") or dict_info.get("praet", "")

                            exs = res.get("examples") or orig_it.get("examples") or build_fallback_examples(raw_w, spoken_w, ar, syn)

                            results.append({
                                "page": orig_page,
                                "word": raw_w,
                                "spoken_word": spoken_w,
                                "youglish_query": yg,
                                "arabic": ar,
                                "synonym": syn,
                                "synonym_list": syn_list,
                                "is_verb": is_v,
                                "perfekt": perf,
                                "praeteritum": praet,
                                "examples": exs
                            })
                        logger.info(f"Successfully enriched {len(results)} items via model {model_name}.")
                        return results
                    else:
                        logger.warning(f"Model {model_name} returned status {resp.status_code}: {resp.text[:100]}. Trying next candidate...")
            except Exception as e:
                logger.warning(f"Exception calling model {model_name}: {e}. Trying next candidate...")

    # Robust Offline Fallback
    logger.info("Enriching batch using offline dictionary and rule-based system.")
    fallback_results = []
    for it in items:
        raw_w = it.get("word", "")
        spoken_w = clean_for_tts(raw_w)
        yg_query = clean_for_youglish(spoken_w)

        dict_info = OFFLINE_GERMAN_ARABIC_DICT.get(spoken_w.lower(), {})
        ar = it.get("arabic") or dict_info.get("ar", "")
        syn = it.get("synonym", "")
        syn_list = [s.strip() for s in re.split(r'[/,]', syn) if s.strip()]

        rule_is_v, rule_perf, rule_praet, rule_ar = rule_based_full_check(raw_w)
        is_verb = bool(it.get("is_verb") or rule_is_v or dict_info)
        perfekt = it.get("perfekt") or dict_info.get("perf") or rule_perf
        praeteritum = it.get("praeteritum") or dict_info.get("praet") or rule_praet
        if not ar:
            ar = rule_ar or spoken_w

        examples = it.get("examples") or build_fallback_examples(raw_w, spoken_w, ar, syn)

        fallback_results.append({
            "page": it.get("page", 1),
            "word": raw_w,
            "spoken_word": spoken_w,
            "youglish_query": yg_query,
            "arabic": ar,
            "synonym": syn,
            "synonym_list": syn_list,
            "is_verb": is_verb,
            "perfekt": perfekt,
            "praeteritum": praeteritum,
            "examples": examples
        })
    return fallback_results
