import json
from typing import Dict, Any, List
from app.db import get_db


def generate_standalone_html(document_id: int) -> str:
    """
    Generates a 100% self-contained standalone HTML file for a given document.
    Works anywhere offline on phones, tablets, or PCs without needing a backend server!
    """
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not doc:
            raise ValueError(f"Document {document_id} not found.")

        words = conn.execute("""
            SELECT w.*, p.is_learned, p.is_review, p.custom_example_de, p.custom_example_ar
            FROM vocabulary_words w
            LEFT JOIN user_progress p ON w.id = p.word_id
            WHERE w.document_id = ?
            ORDER BY w.id ASC
        """, (document_id,)).fetchall()

        # Fetch examples for each word
        examples_rows = conn.execute("""
            SELECT e.*
            FROM word_examples e
            JOIN vocabulary_words w ON e.word_id = w.id
            WHERE w.document_id = ?
            ORDER BY e.word_id, e.order_index
        """, (document_id,)).fetchall()

    doc_title = doc["title"]
    total_words = len(words)

    # Build examples mapping
    examples_map: Dict[int, List[Dict[str, str]]] = {}
    for r in examples_rows:
        w_id = r["word_id"]
        if w_id not in examples_map:
            examples_map[w_id] = []
        examples_map[w_id].append({
            "tag": r["tag"],
            "de": r["de_sentence"],
            "ar": r["ar_sentence"]
        })

    # Prepare words JSON payload
    items_payload = []
    perfekt_map: Dict[int, str] = {}
    learned_ids = []
    review_ids = []
    custom_examples: Dict[int, Dict[str, str]] = {}

    from app.routers.vocab import german_sort_key, classify_case

    for w in words:
        wid = w["id"]
        syn_list = json.loads(w["synonym_list_json"] or "[]")
        is_v = bool(w["is_verb"]) if "is_verb" in w.keys() else bool(w.get("perfekt"))
        c_case = w["grammatical_case"] if ("grammatical_case" in w.keys() and w["grammatical_case"] and w["grammatical_case"] != "none") else classify_case(w["synonym"], w["word"], is_v)
        items_payload.append({
            "id": wid,
            "page_word_num": 1,
            "page": w["page_number"],
            "word": w["word"],
            "spokenWord": w["spoken_word"],
            "youglishQuery": w["youglish_query"],
            "arabic": w["arabic"],
            "synonym": w["synonym"],
            "synonymList": syn_list,
            "grammatical_case": c_case,
            "perfekt": w["perfekt"] or "",
            "praeteritum": w["praeteritum"] or "" if "praeteritum" in w.keys() else "",
            "examples": examples_map.get(wid, [])
        })

        if w["perfekt"]:
            perfekt_map[wid] = w["perfekt"]
        if w["is_learned"]:
            learned_ids.append(wid)
        if w["is_review"]:
            review_ids.append(wid)
        if w["custom_example_de"]:
            custom_examples[wid] = {
                "de": w["custom_example_de"],
                "ar": w["custom_example_ar"] or ""
            }

    # Sort items payload alphabetically and number sequentially from 1 to N
    items_payload.sort(key=lambda x: german_sort_key(x["word"]))
    for idx, it in enumerate(items_payload, 1):
        it["page_word_num"] = idx

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{doc_title} — قاموس ومُعلّم النطق التفاعلي ({total_words} كلمة)</title>
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

  <style>
    body {{
      font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
      background-color: #f8fafc;
      color: #0f172a;
    }}
    .font-german {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    @keyframes pulse-ring {{
      0% {{ box-shadow: 0 0 0 0 rgba(2, 132, 199, 0.55); }}
      70% {{ box-shadow: 0 0 0 10px rgba(2, 132, 199, 0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(2, 132, 199, 0); }}
    }}
    .word-btn-speaking {{
      animation: pulse-ring 1.1s infinite;
      background-color: #e0f2fe !important;
      border-color: #0284c7 !important;
      color: #0369a1 !important;
    }}

    @keyframes sound-wave {{
      0%, 100% {{ transform: scaleY(0.35); }}
      50% {{ transform: scaleY(1); }}
    }}
    .wave-bar {{
      display: inline-block;
      width: 3px;
      height: 14px;
      margin: 0 1px;
      background-color: #0284c7;
      border-radius: 2px;
      animation: sound-wave 0.6s ease-in-out infinite;
    }}
    .wave-bar:nth-child(2) {{ animation-delay: 0.15s; }}
    .wave-bar:nth-child(3) {{ animation-delay: 0.3s; }}

    .card-learned {{
      background-color: #f0fdf4 !important;
      border-color: #86efac !important;
      border-top: 4px solid #10b981 !important;
    }}

    .card-review {{
      background-color: #fffbeb !important;
      border-color: #fcd34d !important;
      border-top: 4px solid #f59e0b !important;
    }}

    .card-default {{
      border-top: 4px solid #0284c7;
    }}

    @media print {{
      body {{ background: #ffffff !important; color: #000000 !important; }}
      .no-print {{ display: none !important; }}
      .print-only {{ display: block !important; }}
      #cards-container {{ display: block !important; }}
      .vocab-card {{
        break-inside: avoid;
        page-break-inside: avoid;
        border: 1px solid #cbd5e1 !important;
        box-shadow: none !important;
        margin-bottom: 6px !important;
        padding: 8px 12px !important;
      }}
    }}
  </style>
</head>
<body class="min-h-screen flex flex-col">

  <!-- Top Header Banner -->
  <header class="bg-slate-900 text-white shadow-lg border-b-4 border-sky-500">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-5 space-y-4">
      <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="bg-sky-500/20 text-sky-300 border border-sky-400/30 text-xs font-bold px-2.5 py-1 rounded-full">{doc_title}</span>
            <span class="bg-teal-500/20 text-teal-300 border border-teal-400/30 text-xs font-bold px-2.5 py-1 rounded-full">⏳ البيرفكت (Perfekt) للأفعال</span>
            <span class="bg-purple-500/20 text-purple-300 border border-purple-400/30 text-xs font-bold px-2.5 py-1 rounded-full">🔊 نطق المرادفات</span>
            <span class="bg-rose-500/20 text-rose-300 border border-rose-400/30 text-xs font-bold px-2.5 py-1 rounded-full">🎬 YouGlish + 🖼️ صور</span>
            <span class="bg-amber-500/20 text-amber-300 border border-amber-400/30 text-xs font-bold px-2.5 py-1 rounded-full">🌐 أمثلة حية مترجمة</span>
          </div>
          <h1 class="text-2xl sm:text-3xl font-extrabold mt-2 tracking-tight">
            قاموس {doc_title} التفاعلي — النطق، البيرفكت، المرادفات، والأمثلة المترجمة
          </h1>
          <p class="text-slate-300 text-sm mt-1">
            اضغط على <strong class="text-sky-300">الكلمة</strong> أو <strong class="text-teal-300">البيرفكت</strong> أو <strong class="text-purple-300">المرادفات</strong> لسماع النطق • واضغط <strong class="text-amber-300">🌐 أمثلة حية</strong> أو <strong class="text-rose-300">🎬 YouGlish</strong> أو <strong class="text-indigo-300">🖼️ صور</strong> لفتحها في نافذة مصغرة عائمة
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2 no-print self-stretch md:self-auto">
          <button id="test-audio-btn" type="button" class="flex items-center justify-center gap-2 bg-sky-600 hover:bg-sky-500 active:bg-sky-700 text-white font-bold text-xs sm:text-sm px-3.5 py-2.5 rounded-xl shadow transition cursor-pointer">
            <span>🔊</span>
            <span>اختبار الصوت</span>
          </button>
          <button id="print-pdf-btn" type="button" class="flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-600 font-bold text-xs sm:text-sm px-3.5 py-2.5 rounded-xl transition cursor-pointer">
            <span>🖨️</span>
            <span>طباعة PDF</span>
          </button>
        </div>
      </div>

      <!-- Progress Bar Card -->
      <div class="bg-slate-800/90 border border-slate-700 rounded-2xl p-3.5 sm:p-4 no-print">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div class="flex items-center gap-2">
            <span class="text-base">🎯</span>
            <span class="text-xs sm:text-sm font-bold text-slate-200">مستوى إنجاز وحفظ الكلمات:</span>
            <span id="progress-badge" class="bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 text-xs font-extrabold px-2.5 py-0.5 rounded-full">0%</span>
          </div>
          <div class="flex flex-wrap items-center gap-3 text-xs font-semibold text-slate-300">
            <span>✅ المحفوظة: <strong id="learned-total-count" class="text-emerald-400">0</strong></span>
            <span>⭐ للمراجعة: <strong id="review-total-count" class="text-amber-400">0</strong></span>
            <span>⏳ المتبقية: <strong id="remaining-total-count" class="text-sky-300">{total_words}</strong></span>
            <span>📚 الإجمالي: <strong class="text-white">{total_words}</strong></span>
          </div>
        </div>
        <div class="w-full h-3 bg-slate-950 rounded-full overflow-hidden border border-slate-700">
          <div id="progress-bar-fill" class="h-full bg-gradient-to-l from-emerald-400 via-teal-500 to-sky-500 transition-all duration-300 rounded-full" style="width: 0%"></div>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-2 mt-2.5 pt-2 border-t border-slate-700/70 text-[11px] text-slate-400">
          <span>💾 يتم حفظ (تم الحفظ ✅) و (للمراجعة ⭐) والأمثلة تلقائياً على متصفحك</span>
          <div class="flex flex-wrap items-center gap-2">
            <button id="mark-visible-btn" type="button" class="text-emerald-300 hover:text-emerald-200 bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-700/50 px-2.5 py-1 rounded-lg font-bold transition cursor-pointer">
              ✅ تحديد المعروض كمحفوظ
            </button>
            <button id="clear-review-btn" type="button" class="text-amber-300 hover:text-amber-200 bg-amber-950/50 hover:bg-amber-900/60 border border-amber-800/50 px-2.5 py-1 rounded-lg font-bold transition cursor-pointer">
              ⭐ إخلاء قائمة المراجعة
            </button>
            <button id="reset-progress-btn" type="button" class="text-rose-300 hover:text-rose-200 bg-rose-950/50 hover:bg-rose-900/60 border border-rose-800/50 px-2.5 py-1 rounded-lg font-bold transition cursor-pointer">
              🗑️ تصفير الكل
            </button>
          </div>
        </div>
      </div>
    </div>
  </header>

  <!-- Sticky Control & Filter Bar -->
  <section class="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200 shadow-sm no-print">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3 space-y-2.5">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-2 items-center">
        <div class="relative lg:col-span-4">
          <input
            id="search-input"
            type="search"
            placeholder="ابحث بالكلمة، البيرفكت، الترجمة، المرادف، أو الرقم..."
            class="w-full pl-9 pr-10 py-2 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition"
          >
          <span class="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">🔍</span>
          <button id="clear-search-btn" type="button" title="مسح البحث" class="hidden absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 text-xs bg-slate-200 px-2 py-0.5 rounded-md">✕</button>
        </div>

        <div class="lg:col-span-2">
          <select id="page-select" aria-label="تصفية حسب الصفحة" class="w-full py-2 px-3 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500 font-semibold text-slate-700 cursor-pointer">
            <option value="all">📄 كل الصفحات</option>
          </select>
        </div>

        <div class="lg:col-span-2">
          <select id="rate-select" aria-label="سرعة النطق" class="w-full py-2 px-3 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500 font-semibold text-slate-700 cursor-pointer">
            <option value="0.95">🎙️ السرعة: طبيعية (0.95x)</option>
            <option value="0.8">🎙️ السرعة: متوسطة (0.80x)</option>
            <option value="0.65">🎙️ السرعة: بطيئة (0.65x)</option>
            <option value="1.1">🎙️ السرعة: سريعة (1.10x)</option>
          </select>
        </div>

        <div class="lg:col-span-2">
          <select id="voice-select" aria-label="اختيار المعلّم الصوتي" class="w-full py-2 px-3 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-700 cursor-pointer" dir="ltr">
            <option value="">🇩🇪 Standard Deutsch (de-DE)</option>
          </select>
        </div>

        <div class="lg:col-span-2 flex rounded-xl bg-slate-100 p-1 border border-slate-200">
          <button id="view-cards-btn" type="button" class="flex-1 py-1.5 px-2 text-xs font-bold rounded-lg bg-white text-sky-700 shadow-sm transition cursor-pointer">
            🗂️ بطاقات
          </button>
          <button id="view-table-btn" type="button" class="flex-1 py-1.5 px-2 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition cursor-pointer">
            📋 جدول
          </button>
        </div>
      </div>

      <!-- Second Filter Row -->
      <div class="flex flex-wrap items-center justify-between gap-2 pt-1">
        <div class="flex flex-wrap items-center gap-1.5" id="status-filters">
          <button type="button" data-status="all" class="status-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer bg-slate-900 text-white border-slate-900 ring-2 ring-offset-1 ring-slate-900">
            📚 الكل (<span>{total_words}</span>)
          </button>
          <button type="button" data-status="verbs" class="status-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer bg-teal-50 text-teal-900 border-teal-300 hover:bg-teal-100">
            ⏳ الأفعال مع البيرفكت (<span id="filter-verbs-count">0</span>)
          </button>
          <button type="button" data-status="review" class="status-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer bg-amber-50 text-amber-900 border-amber-300 hover:bg-amber-100">
            ⭐ للمراجعة (<span id="filter-review-count">0</span>)
          </button>
          <button type="button" data-status="learned" class="status-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer bg-emerald-50 text-emerald-800 border-emerald-300 hover:bg-emerald-100">
            ✅ المحفوظة (<span id="filter-learned-count">0</span>)
          </button>
          <button type="button" data-status="unlearned" class="status-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer bg-sky-50 text-sky-800 border-sky-300 hover:bg-sky-100">
            ⏳ غير المحفوظة (<span id="filter-unlearned-count">{total_words}</span>)
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button id="toggle-all-examples-btn" type="button" class="px-3 py-1.5 rounded-xl text-xs font-bold border border-indigo-300 bg-indigo-50 text-indigo-900 hover:bg-indigo-100 transition cursor-pointer">
            📖 إظهار كل الأمثلة المحلية
          </button>
          <span id="results-counter" class="bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600">
            المعروض: <strong class="text-sky-700">{total_words}</strong> من {total_words}
          </span>
        </div>
      </div>
    </div>
  </section>

  <!-- Main Content Area -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
    <div id="cards-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>

    <div id="table-container" class="hidden bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm text-right border-collapse">
          <thead class="bg-slate-900 text-white text-xs uppercase">
            <tr>
              <th class="py-3.5 px-3 w-20 text-center"># / الصفحة</th>
              <th class="py-3.5 px-3 w-40 text-center">الحفظ والمراجعة</th>
              <th class="py-3.5 px-4 text-left" dir="ltr">🔊 الكلمة + ⏳ البيرفكت + النوافذ المصغرة</th>
              <th class="py-3.5 px-4">الترجمة العربية + 🌐 أمثلة مترجمة</th>
              <th class="py-3.5 px-4 text-left" dir="ltr">🔊 المرادفات (اضغط للنطق)</th>
            </tr>
          </thead>
          <tbody id="table-body" class="divide-y divide-slate-200"></tbody>
        </table>
      </div>
    </div>

    <div id="empty-state" class="hidden text-center py-16 bg-white rounded-2xl border border-slate-200 my-4">
      <div class="text-4xl mb-3">🔎</div>
      <h3 class="text-lg font-bold text-slate-800">لا توجد كلمات مطابقة لبحثك أو للفلتر المحدد</h3>
      <button id="reset-filters-btn" type="button" class="mt-4 bg-sky-600 hover:bg-sky-500 text-white text-sm font-bold px-5 py-2.5 rounded-xl transition cursor-pointer">
        إعادة عرض جميع الكلمات ({total_words})
      </button>
    </div>
  </main>

  <!-- TTS Audio Toast -->
  <div id="tts-toast" class="fixed bottom-5 left-5 z-50 hidden items-center gap-3 bg-slate-900/95 text-white px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 max-w-sm transition-all no-print" dir="ltr">
    <div class="flex items-end h-4 gap-0.5">
      <span class="wave-bar"></span>
      <span class="wave-bar"></span>
      <span class="wave-bar"></span>
    </div>
    <div class="min-w-0">
      <div class="text-[11px] uppercase tracking-wider text-sky-400 font-semibold">Aussprache (de-DE)</div>
      <div id="tts-toast-word" class="text-sm font-bold font-german truncate"></div>
    </div>
  </div>

  <script id="embedded-data" type="application/json">
    {json.dumps(items_payload, ensure_ascii=False)}
  </script>

  <script>
    (function () {{
      'use strict';
      const STORAGE_KEY_PREFIX = 'vocab_tutor_doc_{document_id}_';
      const STORAGE_LEARNED_KEY = STORAGE_KEY_PREFIX + 'learned';
      const STORAGE_REVIEW_KEY = STORAGE_KEY_PREFIX + 'review';
      const STORAGE_CUSTOM_EX_KEY = STORAGE_KEY_PREFIX + 'custom_ex';

      const vocabItems = JSON.parse(document.getElementById('embedded-data').textContent);

      let learnedSet = new Set({json.dumps(learned_ids)});
      let reviewSet = new Set({json.dumps(review_ids)});
      let customExamples = {json.dumps(custom_examples, ensure_ascii=False)};
      let openExampleIds = new Set();
      let exampleVariantIndex = {{}};
      let showAllExamples = false;

      function loadStateFromStorage() {{
        try {{
          const rawLearned = localStorage.getItem(STORAGE_LEARNED_KEY);
          if (rawLearned) {{
            const parsed = JSON.parse(rawLearned);
            if (Array.isArray(parsed)) learnedSet = new Set(parsed.map(Number));
          }}
          const rawReview = localStorage.getItem(STORAGE_REVIEW_KEY);
          if (rawReview) {{
            const parsedRev = JSON.parse(rawReview);
            if (Array.isArray(parsedRev)) reviewSet = new Set(parsedRev.map(Number));
          }}
          const rawEx = localStorage.getItem(STORAGE_CUSTOM_EX_KEY);
          if (rawEx) {{
            const parsedEx = JSON.parse(rawEx);
            if (parsedEx && typeof parsedEx === 'object') customExamples = parsedEx;
          }}
        }} catch (e) {{}}
      }}

      function saveLearnedToStorage() {{
        try {{ localStorage.setItem(STORAGE_LEARNED_KEY, JSON.stringify(Array.from(learnedSet))); }} catch (e) {{}}
      }}

      function saveReviewToStorage() {{
        try {{ localStorage.setItem(STORAGE_REVIEW_KEY, JSON.stringify(Array.from(reviewSet))); }} catch (e) {{}}
      }}

      function saveCustomExamplesToStorage() {{
        try {{ localStorage.setItem(STORAGE_CUSTOM_EX_KEY, JSON.stringify(customExamples)); }} catch (e) {{}}
      }}

      loadStateFromStorage();

      let currentPage = 'all';
      let currentStatus = 'all';
      let currentSearch = '';
      let currentView = 'cards';
      let germanVoices = [];

      const cardsContainer = document.getElementById('cards-container');
      const tableContainer = document.getElementById('table-container');
      const tableBody = document.getElementById('table-body');
      const emptyState = document.getElementById('empty-state');
      const searchInput = document.getElementById('search-input');
      const clearSearchBtn = document.getElementById('clear-search-btn');
      const pageSelect = document.getElementById('page-select');
      const rateSelect = document.getElementById('rate-select');
      const voiceSelect = document.getElementById('voice-select');
      const resultsCounter = document.getElementById('results-counter');
      const viewCardsBtn = document.getElementById('view-cards-btn');
      const viewTableBtn = document.getElementById('view-table-btn');
      const ttsToast = document.getElementById('tts-toast');
      const ttsToastWord = document.getElementById('tts-toast-word');
      const toggleAllExamplesBtn = document.getElementById('toggle-all-examples-btn');

      function getGoogleImagesUrl(spokenWord) {{
        return 'https://www.google.com/search?q=' + encodeURIComponent(spokenWord) + '&udm=2';
      }}

      function getYouGlishUrl(query) {{
        return 'https://youglish.com/pronounce/' + encodeURIComponent(query) + '/german';
      }}

      function getReversoExamplesUrl(query) {{
        return 'https://context.reverso.net/%D8%A7%D9%84%D8%AA%D8%B1%D8%AC%D9%85%D8%A9/%D8%A7%D9%84%D8%A3%D9%84%D9%85%D8%A7%D9%86%D9%8A%D8%A9-%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A%D8%A9/' + encodeURIComponent(query);
      }}

      function getGlosbeExamplesUrl(query) {{
        return 'https://ar.glosbe.com/de/ar/' + encodeURIComponent(query);
      }}

      function openSingleMiniPopup(url, windowName) {{
        const w = Math.min(860, Math.round((window.screen.availWidth || 1200) * 0.74));
        const h = Math.min(640, Math.round((window.screen.availHeight || 800) * 0.78));
        const left = Math.max(20, Math.round(((window.screen.availWidth || 1200) - w) / 2));
        const top = Math.max(35, Math.round(((window.screen.availHeight || 800) - h) / 2));
        const features = `popup=yes,width=${{w}},height=${{h}},left=${{left}},top=${{top}},menubar=no,toolbar=no,location=yes,status=no,resizable=yes,scrollbars=yes`;
        const win = window.open(url, windowName || 'VocabTutorSinglePopup', features);
        if (win && win.focus) win.focus();
      }}

      function updateProgressUI() {{
        const total = vocabItems.length;
        const learnedCount = learnedSet.size;
        const reviewCount = reviewSet.size;
        const verbsCount = vocabItems.filter(i => Boolean(i.perfekt)).length;
        const remainingCount = total - learnedCount;
        const percent = total > 0 ? Math.round((learnedCount / total) * 100) : 0;

        document.getElementById('learned-total-count').textContent = learnedCount;
        document.getElementById('review-total-count').textContent = reviewCount;
        document.getElementById('remaining-total-count').textContent = remainingCount;
        document.getElementById('progress-badge').textContent = `${{percent}}%`;
        document.getElementById('progress-bar-fill').style.width = `${{percent}}%`;

        document.getElementById('filter-verbs-count').textContent = verbsCount;
        document.getElementById('filter-review-count').textContent = reviewCount;
        document.getElementById('filter-learned-count').textContent = learnedCount;
        document.getElementById('filter-unlearned-count').textContent = remainingCount;
      }}

      function initializeFilters() {{
        const pagesSet = new Set();
        vocabItems.forEach(item => pagesSet.add(item.page));

        Array.from(pagesSet).sort((a, b) => a - b).forEach(p => {{
          const countOnPage = vocabItems.filter(i => i.page === p).length;
          const opt = document.createElement('option');
          opt.value = String(p);
          opt.textContent = `صفحة ${{p}} (${{countOnPage}} كلمة)`;
          pageSelect.appendChild(opt);
        }});
      }}

      function loadGermanVoices() {{
        if (!('speechSynthesis' in window)) return;
        const allVoices = window.speechSynthesis.getVoices() || [];
        germanVoices = allVoices.filter(v => v.lang && v.lang.toLowerCase().startsWith('de'));
        voiceSelect.innerHTML = '<option value="">🇩🇪 الصوت الألماني التلقائي (de-DE)</option>';
        germanVoices.forEach((v, idx) => {{
          const opt = document.createElement('option');
          opt.value = String(idx);
          opt.textContent = `🇩🇪 ${{v.name}} (${{v.lang}})`;
          voiceSelect.appendChild(opt);
        }});
      }}

      if ('speechSynthesis' in window) {{
        loadGermanVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {{
          window.speechSynthesis.onvoiceschanged = loadGermanVoices;
        }}
      }}

      function setSpeakingUI(id, spokenText, isSpeaking) {{
        document.querySelectorAll('.word-btn-speaking').forEach(el => el.classList.remove('word-btn-speaking'));
        if (isSpeaking && id !== null) {{
          document.querySelectorAll(`[data-speak-id="${{id}}"]`).forEach(el => el.classList.add('word-btn-speaking'));
          ttsToastWord.textContent = spokenText;
          ttsToast.classList.remove('hidden');
          ttsToast.classList.add('flex');
        }} else {{
          ttsToast.classList.add('hidden');
          ttsToast.classList.remove('flex');
        }}
      }}

      function speakGermanText(id, spokenText) {{
        if (!spokenText) return;
        const rate = parseFloat(rateSelect.value) || 0.95;
        if ('speechSynthesis' in window) {{
          try {{
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(spokenText);
            utterance.lang = 'de-DE';
            utterance.rate = rate;
            const selectedVoiceIndex = voiceSelect.value;
            if (selectedVoiceIndex !== '' && germanVoices[selectedVoiceIndex]) {{
              utterance.voice = germanVoices[selectedVoiceIndex];
            }} else if (germanVoices.length > 0) {{
              utterance.voice = germanVoices.find(v => v.lang === 'de-DE' || v.lang === 'de_DE') || germanVoices[0];
            }}
            utterance.onstart = () => setSpeakingUI(id, spokenText, true);
            utterance.onend = () => setSpeakingUI(null, '', false);
            utterance.onerror = () => setSpeakingUI(null, '', false);
            setSpeakingUI(id, spokenText, true);
            window.speechSynthesis.speak(utterance);
            return;
          }} catch (err) {{}}
        }}
        setSpeakingUI(id, spokenText, true);
        setTimeout(() => setSpeakingUI(null, '', false), 1200);
      }}

      function escapeHTML(str) {{
        return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }}

      function getCurrentExampleForItem(item) {{
        if (customExamples[item.id]) {{
          return {{
            tag: 'مثالي المخصص ✍️',
            de: customExamples[item.id].de,
            ar: customExamples[item.id].ar
          }};
        }}
        const list = item.examples && item.examples.length ? item.examples : [
          {{
            tag: 'سياق B2 تطبيقي',
            de: `In aktuellen Diskussionen spielt der Ausdruck „${{item.spokenWord}}“ eine wichtige Rolle.`,
            ar: `في النقاشات الحالية يلعب التعبير "${{item.spokenWord}}" (${{item.arabic}}) دوراً مهماً.`
          }}
        ];
        const idx = (exampleVariantIndex[item.id] || 0) % list.length;
        return list[idx];
      }}

      function getFilteredItems() {{
        const q = currentSearch.trim().toLowerCase();
        return vocabItems.filter(item => {{
          if (currentPage !== 'all' && item.page !== parseInt(currentPage, 10)) return false;
          if (currentStatus === 'verbs' && !item.perfekt) return false;
          if (currentStatus === 'review' && !reviewSet.has(item.id)) return false;
          if (currentStatus === 'learned' && !learnedSet.has(item.id)) return false;
          if (currentStatus === 'unlearned' && learnedSet.has(item.id)) return false;
          if (!q) return true;
          return String(item.page_word_num || item.id) === q.replace('#', '') ||
            String(item.id) === q.replace('#', '') ||
            item.word.toLowerCase().includes(q) ||
            item.spokenWord.toLowerCase().includes(q) ||
            item.perfekt.toLowerCase().includes(q) ||
            item.arabic.toLowerCase().includes(q) ||
            item.synonym.toLowerCase().includes(q);
        }});
      }}

      function toggleWordLearned(id) {{
        if (learnedSet.has(id)) {{
          learnedSet.delete(id);
        }} else {{
          learnedSet.add(id);
        }}
        saveLearnedToStorage();
        updateProgressUI();
        renderList();
      }}

      function toggleWordReview(id) {{
        if (reviewSet.has(id)) {{
          reviewSet.delete(id);
        }} else {{
          reviewSet.add(id);
        }}
        saveReviewToStorage();
        updateProgressUI();
        renderList();
      }}

      function classifyCase(synonym, word) {{
        const s = `${{synonym || ''}} ${{word || ''}}`.toUpperCase();
        const hasD = /\\+D\\b|\\+DAT\\b|DATIV/.test(s);
        const hasA = /\\+A\\b|\\+AKK\\b|AKKUSATIV/.test(s);
        if (hasD && hasA) return 'both';
        if (hasA) return 'akk';
        if (hasD) return 'dat';
        return 'none';
      }}

      function renderCaseBadgeHTML(item) {{
        const c = item.grammatical_case || classifyCase(item.synonym, item.word);
        if (c === 'akk') {{
          return `
            <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-[11px] font-black bg-sky-100 text-sky-900 border border-sky-300 shadow-xs" title="فعل يأخذ مفعولاً به منصوباً (Akkusativ)">
              <span>🎯</span>
              <span>Akkusativ (+A)</span>
            </span>
          `;
        }}
        if (c === 'dat') {{
          return `
            <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-[11px] font-black bg-purple-100 text-purple-900 border border-purple-300 shadow-xs" title="فعل يأخذ حالة الجر (Dativ)">
              <span>💎</span>
              <span>Dativ (+D)</span>
            </span>
          `;
        }}
        if (c === 'both') {{
          return `
            <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-[11px] font-black bg-gradient-to-r from-sky-100 to-purple-100 text-indigo-950 border border-indigo-300 shadow-xs" title="فعل يأخذ الحالتين: Dativ + Akkusativ">
              <span>🎯+💎</span>
              <span>Dativ + Akkusativ</span>
            </span>
          `;
        }}
        return '';
      }}

      function renderPerfektBadgeHTML(item) {{
        if (!item.perfekt) return '';
        const spokenPerfekt = item.perfekt.replace(/\\//g, ' oder ');
        return `
          <div class="mt-2" dir="ltr">
            <button
              type="button"
              data-speak-custom="${{escapeHTML(spokenPerfekt)}}"
              data-word-id="${{item.id}}"
              title="اضغط لسماع نطق البيرفكت (Perfekt)"
              class="w-full text-left px-3 py-1.5 rounded-xl bg-teal-50/90 hover:bg-teal-600 text-teal-900 hover:text-white border border-teal-200 hover:border-teal-600 transition flex items-center justify-between gap-2 cursor-pointer group"
            >
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-[10px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-teal-200/80 text-teal-950 group-hover:bg-white/20 group-hover:text-white shrink-0">⏳ Perfekt</span>
                <span class="text-xs sm:text-sm font-extrabold font-german truncate">${{escapeHTML(item.perfekt)}}</span>
              </div>
              <span class="text-xs shrink-0 opacity-80 group-hover:opacity-100">🔊 نطق</span>
            </button>
          </div>
        `;
      }}

      function renderSynonymsInteractiveHTML(item) {{
        if (!item.synonym) return '';
        const allSpokenSynonyms = (item.synonymList || []).join(', ');
        return `
          <div class="pt-2.5 border-t border-slate-100">
            <div class="flex items-center justify-between gap-2 mb-1.5">
              <span class="text-[11px] font-bold text-slate-500">المرادفات (اضغط لنطق أي مرادف):</span>
              <button
                type="button"
                data-speak-custom="${{escapeHTML(allSpokenSynonyms)}}"
                data-word-id="${{item.id}}"
                class="no-print text-[11px] font-extrabold bg-purple-50 hover:bg-purple-600 text-purple-800 hover:text-white border border-purple-200 hover:border-purple-600 px-2.5 py-0.5 rounded-lg transition flex items-center gap-1 cursor-pointer shrink-0"
                title="نطق جميع المرادفات بالألمانية"
              >
                <span>🔊</span>
                <span>نطق المرادفات</span>
              </button>
            </div>
            <div class="flex flex-wrap gap-1.5" dir="ltr">
              ${{(item.synonymList || []).map(syn => `
                <button
                  type="button"
                  data-speak-custom="${{escapeHTML(syn)}}"
                  data-word-id="${{item.id}}"
                  title="اضغط لسماع نطق المرادف: ${{escapeHTML(syn)}}"
                  class="text-xs font-semibold font-german bg-slate-100 hover:bg-purple-600 text-slate-700 hover:text-white border border-slate-200 hover:border-purple-600 px-2.5 py-1 rounded-lg transition flex items-center gap-1 cursor-pointer"
                >
                  <span>${{escapeHTML(syn)}}</span>
                  <span class="text-[10px] opacity-70">🔊</span>
                </button>
              `).join('')}}
            </div>
          </div>
        `;
      }}

      function renderExampleBoxHTML(item) {{
        const isOpen = showAllExamples || openExampleIds.has(item.id);
        if (!isOpen) return '';
        const ex = getCurrentExampleForItem(item);
        return `
          <div class="mt-2.5 bg-amber-50/90 border border-amber-200 rounded-xl p-3 space-y-2 no-print">
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <span class="text-[10px] font-extrabold bg-amber-200/80 text-amber-900 px-2 py-0.5 rounded-full">
                📖 ${{escapeHTML(ex.tag)}}
              </span>
              <div class="flex items-center gap-1 flex-wrap">
                <button type="button" data-speak-example="${{item.id}}" data-sentence="${{escapeHTML(ex.de)}}" class="text-[11px] font-bold bg-white hover:bg-sky-600 hover:text-white text-slate-700 border border-slate-200 px-2 py-0.5 rounded-lg transition cursor-pointer">
                  🔊 نطق الجملة
                </button>
                <button type="button" data-cycle-example="${{item.id}}" class="text-[11px] font-bold bg-white hover:bg-amber-500 hover:text-white text-slate-700 border border-slate-200 px-2 py-0.5 rounded-lg transition cursor-pointer" title="تغيير السياق المحلي">
                  🔄 جملة أخرى
                </button>
                <button type="button" data-edit-example="${{item.id}}" class="text-[11px] font-bold bg-white hover:bg-slate-800 hover:text-white text-slate-700 border border-slate-200 px-2 py-0.5 rounded-lg transition cursor-pointer" title="كتابة مثالك الخاص">
                  ✏️
                </button>
              </div>
            </div>
            <p class="text-xs sm:text-sm font-bold font-german text-slate-900 leading-relaxed" dir="ltr">
              ${{escapeHTML(ex.de)}}
            </p>
            <p class="text-xs font-semibold text-amber-950 leading-relaxed border-t border-amber-200/60 pt-1.5">
              ${{escapeHTML(ex.ar)}}
            </p>
            <div class="pt-2 border-t border-amber-200/80 flex flex-wrap items-center justify-between gap-1.5">
              <span class="text-[10px] font-bold text-amber-900">🌐 أمثلة خارجية متنوعة بترجمتها العربية:</span>
              <div class="flex items-center gap-1.5">
                <button type="button" data-popup-type="reverso" data-word-id="${{item.id}}" class="text-[11px] font-extrabold bg-amber-600 hover:bg-amber-700 text-white px-2.5 py-1 rounded-lg shadow-sm transition cursor-pointer">
                  🌐 أمثلة Reverso المترجمة
                </button>
                <button type="button" data-popup-type="glosbe" data-word-id="${{item.id}}" class="text-[11px] font-extrabold bg-teal-700 hover:bg-teal-800 text-white px-2.5 py-1 rounded-lg shadow-sm transition cursor-pointer">
                  📚 أمثلة Glosbe المترجمة
                </button>
              </div>
            </div>
          </div>
        `;
      }}

      function renderList() {{
        const filtered = getFilteredItems();
        resultsCounter.innerHTML = `المعروض: <strong class="text-sky-700">${{filtered.length}}</strong> من ${{vocabItems.length}}`;
        if (filtered.length === 0) {{
          cardsContainer.innerHTML = '';
          tableBody.innerHTML = '';
          emptyState.classList.remove('hidden');
          return;
        }}
        emptyState.classList.add('hidden');

        if (currentView === 'cards') {{
          cardsContainer.classList.remove('hidden');
          tableContainer.classList.add('hidden');
          cardsContainer.innerHTML = filtered.map(item => {{
            const isLearned = learnedSet.has(item.id);
            const isReview = reviewSet.has(item.id);
            const cardStyleClass = isReview ? 'card-review' : (isLearned ? 'card-learned' : 'card-default');

            return `
              <article class="vocab-card bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition p-4 flex flex-col justify-between gap-3 ${{cardStyleClass}}">
                <div>
                  <div class="flex items-center justify-between gap-1.5 mb-2.5 flex-wrap">
                    <div class="flex items-center gap-1.5 flex-wrap">
                      <span class="bg-slate-900 text-white text-xs font-extrabold px-2.5 py-0.5 rounded-lg">#${{item.page_word_num || item.id}}</span>
                      <span class="bg-slate-100 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-lg border border-slate-200">صفحة ${{item.page}}</span>
                      ${{renderCaseBadgeHTML(item)}}
                    </div>

                    <div class="flex items-center gap-1.5 no-print">
                      <button
                        type="button"
                        data-toggle-review="${{item.id}}"
                        class="toggle-review-btn text-xs font-extrabold px-2.5 py-1 rounded-xl border transition cursor-pointer flex items-center gap-1 ${{
                          isReview
                            ? 'bg-amber-500 text-white border-amber-500 shadow-sm hover:bg-amber-600'
                            : 'bg-slate-50 text-slate-600 border-slate-300 hover:bg-amber-50 hover:text-amber-800 hover:border-amber-300'
                        }}"
                      >
                        <span>${{isReview ? '⭐' : '☆'}}</span>
                        <span>${{isReview ? 'للمراجعة' : 'مراجعة'}}</span>
                      </button>

                      <button
                        type="button"
                        data-toggle-learned="${{item.id}}"
                        class="toggle-learned-btn text-xs font-extrabold px-2.5 py-1 rounded-xl border transition cursor-pointer flex items-center gap-1 ${{
                          isLearned
                            ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm hover:bg-emerald-700'
                            : 'bg-slate-50 text-slate-600 border-slate-300 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-300'
                        }}"
                      >
                        <span>${{isLearned ? '✅' : '⭕'}}</span>
                        <span>${{isLearned ? 'تم الحفظ' : 'احفظ'}}</span>
                      </button>
                    </div>
                  </div>

                  <div class="flex items-stretch gap-1.5" dir="ltr">
                    <button type="button" data-speak-id="${{item.id}}" data-spoken="${{escapeHTML(item.spokenWord)}}" class="speak-main-word-btn flex-1 min-w-0 text-left px-3.5 py-3 rounded-xl border-2 border-slate-200 bg-slate-50/70 hover:bg-sky-50/80 hover:border-sky-300 text-slate-900 transition flex items-center justify-between gap-2 cursor-pointer group">
                      <div class="min-w-0 flex-1">
                        <div class="text-base sm:text-lg font-bold font-german tracking-tight break-words group-hover:text-sky-700 transition">${{escapeHTML(item.word)}}</div>
                        <div class="text-[11px] text-slate-500 font-german mt-0.5">النطق: <span class="font-semibold text-slate-700">${{escapeHTML(item.spokenWord)}}</span></div>
                      </div>
                      <span class="w-9 h-9 rounded-xl bg-white border border-slate-200 shadow-sm flex items-center justify-center text-base shrink-0 group-hover:bg-sky-600 group-hover:text-white transition">🔊</span>
                    </button>

                    <button type="button" data-popup-type="youglish" data-word-id="${{item.id}}" title="فتح YouGlish في نافذة مصغرة عائمة" class="no-print px-2.5 rounded-xl border-2 border-rose-200 bg-rose-50/80 hover:bg-rose-600 hover:border-rose-600 text-rose-800 hover:text-white transition flex flex-col items-center justify-center gap-1 shrink-0 shadow-sm cursor-pointer">
                      <span class="text-base leading-none">🎬</span>
                      <span class="text-[10px] font-extrabold leading-none font-german">YouGlish</span>
                    </button>

                    <button type="button" data-popup-type="images" data-word-id="${{item.id}}" title="فتح صور Google في نافذة مصغرة عائمة" class="no-print px-2.5 rounded-xl border-2 border-indigo-200 bg-indigo-50/80 hover:bg-indigo-600 hover:border-indigo-600 text-indigo-800 hover:text-white transition flex flex-col items-center justify-center gap-1 shrink-0 shadow-sm cursor-pointer">
                      <span class="text-base leading-none">🖼️</span>
                      <span class="text-[10px] font-extrabold leading-none">صور</span>
                    </button>
                  </div>

                  ${{renderPerfektBadgeHTML(item)}}

                  <div class="mt-3 bg-sky-50/70 border border-sky-100 rounded-xl px-3.5 py-2.5">
                    <div class="flex items-center justify-between gap-1.5 mb-1 flex-wrap">
                      <span class="text-[11px] font-bold text-sky-700">الترجمة العربية:</span>
                      <div class="flex items-center gap-1 no-print flex-wrap">
                        <button type="button" data-popup-type="reverso" data-word-id="${{item.id}}" class="text-[11px] font-extrabold text-white bg-amber-600 hover:bg-amber-700 px-2 py-0.5 rounded-lg shadow-sm transition cursor-pointer flex items-center gap-1">
                          <span>🌐</span>
                          <span>أمثلة حية مترجمة</span>
                        </button>
                        <button type="button" data-toggle-example="${{item.id}}" class="text-[11px] font-extrabold text-amber-900 bg-amber-100/90 hover:bg-amber-200 border border-amber-300 px-2 py-0.5 rounded-lg transition cursor-pointer">
                          📖 مثال B2
                        </button>
                      </div>
                    </div>
                    <div class="text-sm sm:text-base font-bold text-slate-900 leading-snug">${{escapeHTML(item.arabic)}}</div>
                  </div>

                  ${{renderExampleBoxHTML(item)}}
                </div>

                ${{renderSynonymsInteractiveHTML(item)}}
              </article>
            `;
          }}).join('');
        }} else {{
          cardsContainer.classList.add('hidden');
          tableContainer.classList.remove('hidden');
          tableBody.innerHTML = filtered.map(item => {{
            const isLearned = learnedSet.has(item.id);
            const isReview = reviewSet.has(item.id);
            const rowBg = isReview ? 'bg-amber-50/60' : (isLearned ? 'bg-emerald-50/40' : '');

            return `
              <tr class="hover:bg-slate-50/80 transition ${{rowBg}}">
                <td class="py-2.5 px-3 text-center align-middle whitespace-nowrap">
                  <div class="font-extrabold text-slate-900 text-xs">#${{item.page_word_num || item.id}}</div>
                  <div class="text-[11px] text-slate-500">ص ${{item.page}}</div>
                </td>
                <td class="py-2.5 px-3 text-center align-middle whitespace-nowrap">
                  <div class="flex items-center justify-center gap-1.5">
                    <button
                      type="button"
                      data-toggle-review="${{item.id}}"
                      class="toggle-review-btn text-xs font-extrabold px-2 py-1.5 rounded-xl border transition cursor-pointer inline-flex items-center gap-1 ${{
                        isReview
                          ? 'bg-amber-500 text-white border-amber-500'
                          : 'bg-slate-50 text-slate-600 border-slate-300 hover:bg-amber-50 hover:text-amber-800'
                      }}"
                    >
                      <span>${{isReview ? '⭐' : '☆'}}</span>
                      <span>مراجعة</span>
                    </button>
                    <button
                      type="button"
                      data-toggle-learned="${{item.id}}"
                      class="toggle-learned-btn text-xs font-extrabold px-2 py-1.5 rounded-xl border transition cursor-pointer inline-flex items-center gap-1 ${{
                        isLearned
                          ? 'bg-emerald-600 text-white border-emerald-600'
                          : 'bg-slate-50 text-slate-600 border-slate-300 hover:bg-emerald-50 hover:text-emerald-700'
                      }}"
                    >
                      <span>${{isLearned ? '✅' : '⭕'}}</span>
                      <span>${{isLearned ? 'محفوظة' : 'احفظ'}}</span>
                    </button>
                  </div>
                </td>
                <td class="py-2.5 px-4 align-middle" dir="ltr">
                  <div class="flex items-center gap-1.5">
                    <button type="button" data-speak-id="${{item.id}}" data-spoken="${{escapeHTML(item.spokenWord)}}" class="speak-main-word-btn flex-1 min-w-0 text-left px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-sky-50 transition flex items-center justify-between gap-2 cursor-pointer group">
                      <span class="font-bold font-german text-sm group-hover:text-sky-700">${{escapeHTML(item.word)}}</span>
                      <span class="w-7 h-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-xs shrink-0 group-hover:bg-sky-600 group-hover:text-white transition">🔊</span>
                    </button>
                    <button type="button" data-popup-type="youglish" data-word-id="${{item.id}}" class="no-print px-2.5 py-2 rounded-xl border border-rose-200 bg-rose-50/80 hover:bg-rose-600 hover:border-rose-600 text-rose-800 hover:text-white transition flex items-center justify-center gap-1 text-xs font-bold shrink-0 shadow-sm cursor-pointer">
                      <span>🎬</span><span class="font-german">YouGlish</span>
                    </button>
                    <button type="button" data-popup-type="images" data-word-id="${{item.id}}" class="no-print px-2.5 py-2 rounded-xl border border-indigo-200 bg-indigo-50/80 hover:bg-indigo-600 hover:border-indigo-600 text-indigo-800 hover:text-white transition flex items-center justify-center gap-1 text-xs font-bold shrink-0 shadow-sm cursor-pointer">
                      <span>🖼️</span><span>صور</span>
                    </button>
                  </div>
                  <div class="mt-1">${{renderCaseBadgeHTML(item)}}</div>
                  ${{renderPerfektBadgeHTML(item)}}
                </td>
                <td class="py-2.5 px-4 align-middle">
                  <div class="flex items-center justify-between gap-2 flex-wrap">
                    <span class="font-bold text-slate-900 text-sm">${{escapeHTML(item.arabic)}}</span>
                    <div class="flex items-center gap-1 no-print">
                      <button type="button" data-popup-type="reverso" data-word-id="${{item.id}}" class="text-[11px] font-extrabold text-white bg-amber-600 hover:bg-amber-700 px-2 py-0.5 rounded-lg shadow-sm transition cursor-pointer shrink-0">
                        🌐 أمثلة حية
                      </button>
                      <button type="button" data-toggle-example="${{item.id}}" class="text-[11px] font-extrabold text-amber-800 bg-amber-100 hover:bg-amber-200 border border-amber-300 px-2 py-0.5 rounded-lg transition cursor-pointer shrink-0">
                        📖 مثال
                      </button>
                    </div>
                  </div>
                  ${{renderExampleBoxHTML(item)}}
                </td>
                <td class="py-2.5 px-4 align-middle" dir="ltr">
                  <div class="flex flex-wrap items-center gap-1">
                    ${{(item.synonymList || []).map(syn => `
                      <button
                        type="button"
                        data-speak-custom="${{escapeHTML(syn)}}"
                        data-word-id="${{item.id}}"
                        class="text-xs font-semibold font-german bg-slate-100 hover:bg-purple-600 text-slate-700 hover:text-white border border-slate-200 px-2 py-0.5 rounded-lg transition flex items-center gap-1 cursor-pointer"
                      >
                        <span>${{escapeHTML(syn)}}</span>
                        <span class="text-[10px]">🔊</span>
                      </button>
                    `).join('')}}
                  </div>
                </td>
              </tr>
            `;
          }}).join('');
        }}
      }}

      document.addEventListener('click', function (e) {{
        const popupBtn = e.target.closest('[data-popup-type]');
        if (popupBtn) {{
          const wordId = parseInt(popupBtn.getAttribute('data-word-id'), 10);
          const popupType = popupBtn.getAttribute('data-popup-type');
          const item = vocabItems.find(i => i.id === wordId);
          if (!item) return;

          if (popupType === 'images') {{
            openSingleMiniPopup(getGoogleImagesUrl(item.spokenWord), 'GoogleImagesMiniPopup');
          }} else if (popupType === 'youglish') {{
            openSingleMiniPopup(getYouGlishUrl(item.youglishQuery), 'YouGlishMiniPopup');
          }} else if (popupType === 'reverso') {{
            openSingleMiniPopup(getReversoExamplesUrl(item.youglishQuery), 'ReversoExamplesMiniPopup');
          }} else if (popupType === 'glosbe') {{
            openSingleMiniPopup(getGlosbeExamplesUrl(item.youglishQuery), 'GlosbeExamplesMiniPopup');
          }}
          return;
        }}

        const customSpeakBtn = e.target.closest('[data-speak-custom]');
        if (customSpeakBtn) {{
          const wordId = parseInt(customSpeakBtn.getAttribute('data-word-id'), 10);
          const textToSpeak = customSpeakBtn.getAttribute('data-speak-custom');
          speakGermanText(wordId, textToSpeak);
          return;
        }}

        const wordBtn = e.target.closest('.speak-main-word-btn');
        if (wordBtn) {{
          speakGermanText(parseInt(wordBtn.getAttribute('data-speak-id'), 10), wordBtn.getAttribute('data-spoken'));
          return;
        }}

        const learnedBtn = e.target.closest('.toggle-learned-btn');
        if (learnedBtn) {{
          toggleWordLearned(parseInt(learnedBtn.getAttribute('data-toggle-learned'), 10));
          return;
        }}

        const reviewBtn = e.target.closest('.toggle-review-btn');
        if (reviewBtn) {{
          toggleWordReview(parseInt(reviewBtn.getAttribute('data-toggle-review'), 10));
          return;
        }}

        const toggleExBtn = e.target.closest('[data-toggle-example]');
        if (toggleExBtn) {{
          const id = parseInt(toggleExBtn.getAttribute('data-toggle-example'), 10);
          if (openExampleIds.has(id)) {{
            openExampleIds.delete(id);
          }} else {{
            openExampleIds.add(id);
          }}
          renderList();
          return;
        }}

        const speakExBtn = e.target.closest('[data-speak-example]');
        if (speakExBtn) {{
          const id = parseInt(speakExBtn.getAttribute('data-speak-example'), 10);
          const sentence = speakExBtn.getAttribute('data-sentence');
          speakGermanText(id, sentence);
          return;
        }}

        const cycleExBtn = e.target.closest('[data-cycle-example]');
        if (cycleExBtn) {{
          const id = parseInt(cycleExBtn.getAttribute('data-cycle-example'), 10);
          delete customExamples[id];
          saveCustomExamplesToStorage();
          exampleVariantIndex[id] = ((exampleVariantIndex[id] || 0) + 1) % 3;
          renderList();
          return;
        }}

        const editExBtn = e.target.closest('[data-edit-example]');
        if (editExBtn) {{
          const id = parseInt(editExBtn.getAttribute('data-edit-example'), 10);
          const item = vocabItems.find(i => i.id === id);
          if (!item) return;
          const current = getCurrentExampleForItem(item);
          const newDe = window.prompt('اكتب جملة المثال باللغة الألمانية:', current.de);
          if (newDe && newDe.trim()) {{
            const newAr = window.prompt('اكتب الترجمة العربية للمثال:', current.ar) || '';
            customExamples[id] = {{ de: newDe.trim(), ar: newAr.trim() }};
            saveCustomExamplesToStorage();
            renderList();
          }}
        }}
      }});

      toggleAllExamplesBtn.addEventListener('click', function () {{
        showAllExamples = !showAllExamples;
        this.textContent = showAllExamples ? '🙈 إخفاء كل الأمثلة المحلية' : '📖 إظهار كل الأمثلة المحلية';
        renderList();
      }});

      searchInput.addEventListener('input', function () {{
        currentSearch = this.value;
        clearSearchBtn.classList.toggle('hidden', !currentSearch);
        renderList();
      }});

      clearSearchBtn.addEventListener('click', function () {{
        searchInput.value = '';
        currentSearch = '';
        this.classList.add('hidden');
        renderList();
        searchInput.focus();
      }});

      pageSelect.addEventListener('change', function () {{ currentPage = this.value; renderList(); }});

      document.querySelectorAll('.status-filter-btn').forEach(btn => {{
        btn.addEventListener('click', function () {{
          currentStatus = this.getAttribute('data-status');
          document.querySelectorAll('.status-filter-btn').forEach(b => {{
            b.classList.remove('ring-2', 'ring-offset-1', 'ring-slate-900', 'scale-105');
          }});
          this.classList.add('ring-2', 'ring-offset-1', 'ring-slate-900', 'scale-105');
          renderList();
        }});
      }});

      document.getElementById('mark-visible-btn').addEventListener('click', function () {{
        const visible = getFilteredItems();
        if (visible.length === 0) return;
        visible.forEach(item => learnedSet.add(item.id));
        saveLearnedToStorage();
        updateProgressUI();
        renderList();
      }});

      document.getElementById('clear-review-btn').addEventListener('click', function () {{
        if (reviewSet.size === 0) return;
        if (window.confirm('هل تريد إزالة جميع الكلمات من قائمة المراجعة ⭐؟')) {{
          reviewSet.clear();
          saveReviewToStorage();
          updateProgressUI();
          renderList();
        }}
      }});

      document.getElementById('reset-progress-btn').addEventListener('click', function () {{
        if (learnedSet.size === 0 && reviewSet.size === 0) return;
        if (window.confirm('هل أنت متأكد من تصفير جميع الكلمات المحفوظة وقائمة المراجعة والبدء من جديد؟')) {{
          learnedSet.clear();
          reviewSet.clear();
          saveLearnedToStorage();
          saveReviewToStorage();
          updateProgressUI();
          renderList();
        }}
      }});

      viewCardsBtn.addEventListener('click', function () {{
        currentView = 'cards';
        viewCardsBtn.className = 'flex-1 py-1.5 px-2 text-xs font-bold rounded-lg bg-white text-sky-700 shadow-sm transition cursor-pointer';
        viewTableBtn.className = 'flex-1 py-1.5 px-2 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition cursor-pointer';
        renderList();
      }});

      viewTableBtn.addEventListener('click', function () {{
        currentView = 'table';
        viewTableBtn.className = 'flex-1 py-1.5 px-2 text-xs font-bold rounded-lg bg-white text-sky-700 shadow-sm transition cursor-pointer';
        viewCardsBtn.className = 'flex-1 py-1.5 px-2 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition cursor-pointer';
        renderList();
      }});

      document.getElementById('reset-filters-btn').addEventListener('click', function () {{
        currentPage = 'all';
        currentStatus = 'all';
        currentSearch = '';
        searchInput.value = '';
        pageSelect.value = 'all';
        clearSearchBtn.classList.add('hidden');
        renderList();
      }});

      document.getElementById('test-audio-btn').addEventListener('click', () => speakGermanText(vocabItems[0]?.id || 1, vocabItems[0]?.word || '{doc_title}'));
      document.getElementById('print-pdf-btn').addEventListener('click', () => window.print());

      initializeFilters();
      updateProgressUI();
      renderList();
    }})();
  </script>
</body>
</html>
"""
    return html
