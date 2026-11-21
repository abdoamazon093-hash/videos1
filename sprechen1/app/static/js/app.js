/**
 * app.js - المنسق العام للتطبيق وربط الواجهة بالـ FastAPI
 * يربط التعرف الصوتي وقفل الجمل والحافظة الدائمة والمساعد الذكي
 */

document.addEventListener('DOMContentLoaded', () => {
  // ==================== التهيئة والعناصر ====================
  const micBtn = document.getElementById('micBtn');
  const micStatus = document.getElementById('micStatus');
  const langSelect = document.getElementById('langSelect');
  const textInput = document.getElementById('textInput');
  const interimBox = document.getElementById('interimBox');
  
  // أقسام العرض
  const redBox = document.getElementById('redBox');
  const greenBox = document.getElementById('greenBox');
  const greenWordsContainer = document.getElementById('greenWordsContainer');
  const arabicTranslation = document.getElementById('arabicTranslation');
  const whySummary = document.getElementById('whySummary');
  const replacementsList = document.getElementById('replacementsList');
  const radarContainer = document.getElementById('radarContainer');
  const lockedTurnsList = document.getElementById('lockedTurnsList');

  // المساعد الذكي
  const aiInput = document.getElementById('aiInput');
  const aiAskBtn = document.getElementById('aiAskBtn');
  const aiResponseBox = document.getElementById('aiResponseBox');

  // الحافظة الدائمة
  const vaultList = document.getElementById('vaultList');
  const vaultCount = document.getElementById('vaultCount');
  const vaultFilter = document.getElementById('vaultFilter');
  const exportDocxBtn = document.getElementById('exportDocxBtn');
  const exportJsonBtn = document.getElementById('exportJsonBtn');
  const importJsonBtn = document.getElementById('importJsonBtn');
  const importFileInput = document.getElementById('importFileInput');

  // النوافذ المنبثقة
  const toastBox = document.getElementById('toastBox');
  const toastText = document.getElementById('toastText');
  const wordPopup = document.getElementById('wordMeaningPopup');
  const popupGermanWord = document.getElementById('popupGermanWord');
  const popupArabicMeaning = document.getElementById('popupArabicMeaning');
  const guideModal = document.getElementById('guideModal');

  let currentPopupData = { word: '', meaning: '' };
  let currentCorrectedSentence = '';
  let clipsCache = [];

  // ==================== نظام الإشعارات العائمة ====================
  let toastTimer = null;
  function showToast(message, isError = false) {
    if (toastTimer) clearTimeout(toastTimer);
    toastText.textContent = message;
    toastBox.style.borderColor = isError ? '#E11D48' : '#10B981';
    toastBox.classList.remove('hidden');
    toastTimer = setTimeout(() => {
      toastBox.classList.add('hidden');
    }, 3200);
  }

  // ==================== فحص صحة النظام (Health Check) ====================
  async function checkSystemHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        const geminiBadge = document.getElementById('badgeGemini');
        if (geminiBadge) {
          if (data.gemini_configured) {
            geminiBadge.className = 'status-badge green';
            geminiBadge.innerHTML = '<span>●</span> <span>Gemini API سحابي نشط</span>';
          } else {
            geminiBadge.className = 'status-badge sky';
            geminiBadge.innerHTML = '<span>●</span> <span>محرك القواعد المحلي B2/C1</span>';
          }
        }
      }
    } catch (e) {
      console.warn('Health check failed:', e);
    }
  }

  // ==================== مدير قفل الجمل (Sentence Locking) ====================
  const lockingManager = new SentenceLockingManager({
    onActiveUpdate: (text, isProcessing) => {
      if (isProcessing) {
        interimBox.classList.remove('hidden');
        interimBox.textContent = `⏳ جاري التدقيق السياقي الذكي: "${text}"...`;
      } else {
        interimBox.classList.remove('hidden');
        interimBox.textContent = `🎙️ ${text}`;
      }
    },
    onLockTurn: (turnResult) => {
      interimBox.classList.add('hidden');
      interimBox.textContent = '';
      textInput.value = '';
      renderActiveTurn(turnResult);
      prependLockedTurnCard(turnResult);
      showToast('تم التدقيق وقفل الجملة بنجاح ✓');
    },
    onError: (errMsg) => {
      interimBox.classList.remove('hidden');
      interimBox.textContent = `⚠️ ${errMsg}`;
      showToast(errMsg, true);
    }
  });

  // ==================== معالجة التعرف الصوتي ====================
  window.speechEngine.onStatusChangeCallback = (isListening) => {
    if (isListening) {
      micBtn.classList.add('mic-recording');
      micBtn.innerHTML = '<span>⏹️</span> <span>إيقاف المايك</span>';
      micStatus.innerHTML = '<span class="status-badge green"><span>●</span> المايك يستمع الآن...</span>';
    } else {
      micBtn.classList.remove('mic-recording');
      micBtn.innerHTML = '<span>🎙️</span> <span>تحدث بالمايك</span>';
      micStatus.innerHTML = '<span class="text-slate-500">المايك متوقف</span>';
    }
  };

  window.speechEngine.onErrorCallback = (msg, isFatal) => {
    showToast(msg, true);
    if (isFatal) {
      micStatus.innerHTML = `<span style="color:#E11D48; font-weight:700;">${msg}</span>`;
    }
  };

  window.speechEngine.onInterimCallback = (interimText) => {
    lockingManager.feedInterim(interimText);
  };

  window.speechEngine.onFinalCallback = (finalText) => {
    lockingManager.feedFinal(finalText);
  };

  micBtn.addEventListener('click', () => {
    window.speechEngine.toggle();
  });

  langSelect.addEventListener('change', (e) => {
    window.speechEngine.setLanguage(e.target.value);
    showToast(`تم تبديل لغة الصوت إلى: ${e.target.options[e.target.selectedIndex].text}`);
  });

  // الكتابة اليدوية مع إيقاف الحرق والتصحيح التلقائي بعد 650ms
  textInput.addEventListener('input', (e) => {
    lockingManager.feedTyping(e.target.value);
  });

  // ==================== رسم الجولة النشطة (Targeted DOM Update) ====================
  function renderActiveTurn(result) {
    currentCorrectedSentence = result.corrected_german;

    // 1. القسم الأحمر (التشطيب السياقي)
    renderRedSection(result);

    // 2. القسم الأخضر (الكلمات القابلة للضغط)
    renderGreenSection(result);

    // 3. جدول الكلمات المستبدلة
    renderReplacements(result.replaced_words);

    // 4. رادار القواعد
    renderRadar(result.radar_rules);
  }

  function renderRedSection(result) {
    if (result.is_correct) {
      redBox.innerHTML = `<div class="strikethrough-content" style="background:#ECFDF5; border-color:#A7F3D0; color:#065F46;">
        ✓ جملتك سليمة ولا تحتوي على أخطاء سياقية أو قواعدية: "${escapeHtml(result.user_sentence)}"
      </div>`;
      return;
    }

    let userText = result.user_sentence;
    // استبدال الكلمات الخطأ بوسوم تشطيب
    if (result.replaced_words && result.replaced_words.length > 0) {
      result.replaced_words.forEach(rep => {
        if (rep.wrong_or_arabic) {
          const regex = new RegExp(`(${escapeRegExp(rep.wrong_or_arabic)})`, 'gi');
          userText = userText.replace(regex, `<span class="strike-wrong" title="${escapeHtml(rep.why_replaced)}">$1</span>`);
        }
      });
    }

    redBox.innerHTML = `<div class="strikethrough-content">${userText}</div>`;
  }

  function renderGreenSection(result) {
    greenWordsContainer.innerHTML = '';
    const words = result.corrected_german.split(/\s+/);

    words.forEach(w => {
      if (!w) return;
      const cleanWord = w.replace(/[.,/#!$%^&*;:{}=\-_`~()]/g, '');
      const span = document.createElement('span');
      span.className = 'word-chip';
      span.textContent = w + ' ';
      span.title = 'اضغط لمعرفة المعنى والنطق وحفظ الكلمة';
      span.addEventListener('click', (e) => {
        openWordPopup(e, cleanWord, result.corrected_german);
      });
      greenWordsContainer.appendChild(span);
    });

    // الترجمة مع علم مصر 🇪🇬
    arabicTranslation.innerHTML = `<span>🇪🇬</span> <span>${escapeHtml(result.arabic_meaning)}</span>`;
    whySummary.innerHTML = `<span>💡</span> <span>${escapeHtml(result.why_summary)}</span>`;
  }

  function renderReplacements(reps) {
    if (!reps || reps.length === 0) {
      replacementsList.innerHTML = '<div style="padding:12px; font-size:0.85rem; color:#059669; text-align:center;">✓ لم يتم رصد أي أخطاء تتطلب الاستبدال.</div>';
      return;
    }

    let html = '';
    reps.forEach(r => {
      html += `
        <div class="replacement-item">
          <div class="rep-wrong">${escapeHtml(r.wrong_or_arabic)}</div>
          <div style="color:#64748B; font-size:12px;">➔</div>
          <div class="rep-right">${escapeHtml(r.right_german)}</div>
          <div class="rep-why">سبب التعديل: ${escapeHtml(r.why_replaced)}</div>
        </div>
      `;
    });
    replacementsList.innerHTML = html;
  }

  function renderRadar(rules) {
    if (!rules || rules.length === 0) {
      radarContainer.innerHTML = '<div style="font-size:0.8rem; color:#64748B;">لا توجد تراكيب B2/C1 خاصة مرصودة في هذه الجملة.</div>';
      return;
    }

    let html = '';
    rules.forEach(rule => {
      const exDe = rule.examples && rule.examples[0] ? rule.examples[0].de : '';
      const exAr = rule.examples && rule.examples[0] ? rule.examples[0].ar : '';
      html += `
        <div class="radar-card">
          <div class="radar-header">
            <span class="radar-name">${escapeHtml(rule.rule_name)}</span>
            <span class="radar-level">${escapeHtml(rule.level || 'B2')}</span>
          </div>
          <div class="radar-exp">${escapeHtml(rule.explanation)}</div>
          ${exDe ? `<div class="radar-example">🇩🇪 ${escapeHtml(exDe)} <br><span style="color:#059669;">🇪🇬 ${escapeHtml(exAr)}</span></div>` : ''}
        </div>
      `;
    });
    radarContainer.innerHTML = html;
  }

  // ==================== قائمة الجمل المقفولة (Locked Turns) ====================
  function prependLockedTurnCard(result) {
    const card = document.createElement('div');
    card.className = 'locked-card anim-fade-in';
    card.innerHTML = `
      <div class="locked-header">
        <span>🔒 جملة مثبتة ومحفوظة</span>
        <span>${new Date().toLocaleTimeString('ar-EG', {hour: '2-digit', minute:'2-digit'})}</span>
      </div>
      <div class="locked-de">${escapeHtml(result.corrected_german)}</div>
      <div class="locked-ar">🇪🇬 ${escapeHtml(result.arabic_meaning)}</div>
    `;
    lockedTurnsList.prepend(card);
  }

  // ==================== نافذة المعنى الفوري للكلمة (Word Popup) ====================
  async function openWordPopup(event, word, contextSentence) {
    const rect = event.target.getBoundingClientRect();
    currentPopupData.word = word;
    popupGermanWord.textContent = word;
    popupArabicMeaning.textContent = 'جاري البحث...';

    // تموضع النافذة بجوار الكلمة
    let top = rect.bottom + window.scrollY + 8;
    let left = rect.left + window.scrollX - 50;
    if (left + 320 > window.innerWidth) left = window.innerWidth - 330;
    if (left < 10) left = 10;

    wordPopup.style.top = `${top}px`;
    wordPopup.style.left = `${left}px`;
    wordPopup.classList.remove('hidden');

    // جلب المعنى من الباك اند أو القاموس
    try {
      const res = await fetch(`/api/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: word })
      });
      if (res.ok) {
        const data = await res.json();
        currentPopupData.meaning = data.arabic_meaning;
        popupArabicMeaning.textContent = data.arabic_meaning;
      } else {
        popupArabicMeaning.textContent = 'معنى سياقي ألماني';
      }
    } catch (e) {
      popupArabicMeaning.textContent = 'معنى سياقي ألماني';
    }
  }

  window.closeWordMeaningPopup = () => {
    wordPopup.classList.add('hidden');
  };

  window.speakPopupWord = () => {
    if (currentPopupData.word) {
      window.speechEngine.speakGerman(currentPopupData.word);
    }
  };

  window.savePopupWordToClip = async () => {
    if (!currentPopupData.word) return;
    await addClipToBackend({
      text: currentPopupData.word,
      arabic_meaning: currentPopupData.meaning,
      label: 'Wort',
      grammar_notes: 'حفظ من النص الأخضر'
    });
    closeWordMeaningPopup();
  };

  window.copyPopupWordWithMeaning = () => {
    const text = `${currentPopupData.word} = ${currentPopupData.meaning}`;
    navigator.clipboard.writeText(text);
    showToast('تم نسخ الكلمة ومعناها 📋');
  };

  // إغلاق النافذة عند الضغط خارجها
  document.addEventListener('click', (e) => {
    if (!wordPopup.contains(e.target) && !e.target.classList.contains('word-chip')) {
      closeWordMeaningPopup();
    }
  });

  // ==================== أزرار التحكم في الجملة الخضراء ====================
  document.getElementById('speakSentenceBtn').addEventListener('click', () => {
    if (currentCorrectedSentence) {
      window.speechEngine.speakGerman(currentCorrectedSentence);
    }
  });

  document.getElementById('copySentenceBtn').addEventListener('click', () => {
    if (currentCorrectedSentence) {
      navigator.clipboard.writeText(currentCorrectedSentence);
      showToast('تم نسخ الجملة الألمانية المصححة 📋');
    }
  });

  document.getElementById('saveSentenceToClipBtn').addEventListener('click', async () => {
    if (!currentCorrectedSentence) return;
    await addClipToBackend({
      text: currentCorrectedSentence,
      arabic_meaning: arabicTranslation.textContent.replace('🇪🇬', '').trim(),
      label: 'Satz',
      grammar_notes: whySummary.textContent.replace('💡', '').trim()
    });
  });

  // ==================== المساعد الذكي (AI Assistant) ====================
  async function askAiAssistant(questionText) {
    const q = questionText.trim();
    if (!q) return;

    aiResponseBox.innerHTML = '<span style="color:#0284C7; font-weight:700;">🤖 جاري التفكير وصياغة الشرح المختصر...</span>';

    try {
      const res = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          current_sentence: currentCorrectedSentence
        })
      });

      if (!res.ok) throw new Error('فشل استرجاع إجابة المساعد الذكي.');

      const data = await res.json();
      let html = `<div style="font-weight:700; color:#0F172A; margin-bottom:8px;">${escapeHtml(data.answer_ar)}</div>`;
      if (data.german_highlight) {
        html += `<div style="background:#FFFFFF; border:1px solid #CBD5E1; padding:8px; border-radius:6px; direction:ltr; text-align:left; font-family:'Lexend',sans-serif; color:#0369A1; margin-bottom:8px; font-weight:600;">🇩🇪 ${escapeHtml(data.german_highlight)}</div>`;
      }
      if (data.examples && data.examples.length > 0) {
        html += '<div style="font-size:0.8rem; color:#475569;"><strong>أمثلة توضيحية:</strong><ul>';
        data.examples.forEach(ex => {
          html += `<li><span dir="ltr" style="font-family:'Lexend'; font-weight:600;">${escapeHtml(ex.de)}</span> = 🇪🇬 ${escapeHtml(ex.ar)}</li>`;
        });
        html += '</ul></div>';
      }

      aiResponseBox.innerHTML = html;
    } catch (e) {
      aiResponseBox.innerHTML = `<span style="color:#E11D48;">⚠️ ${e.message}</span>`;
    }
  }

  aiAskBtn.addEventListener('click', () => {
    askAiAssistant(aiInput.value);
  });

  document.querySelectorAll('.chip-ai').forEach(chip => {
    chip.addEventListener('click', (e) => {
      const q = e.target.getAttribute('data-q');
      aiInput.value = q;
      askAiAssistant(q);
    });
  });

  // ==================== الحافظة الدائمة (Permanent Vault - SQLite) ====================
  async function loadClips() {
    try {
      const res = await fetch('/api/clips');
      if (res.ok) {
        clipsCache = await res.json();
        renderVault();
      }
    } catch (e) {
      console.warn('Failed to fetch clips:', e);
    }
  }

  function renderVault(filterText = '') {
    const filter = filterText.toLowerCase().trim();
    const filtered = filter ? clipsCache.filter(c => 
      (c.text && c.text.toLowerCase().includes(filter)) || 
      (c.arabic_meaning && c.arabic_meaning.toLowerCase().includes(filter)) ||
      (c.label && c.label.toLowerCase().includes(filter))
    ) : clipsCache;

    vaultCount.textContent = `(${filtered.length})`;

    if (filtered.length === 0) {
      vaultList.innerHTML = '<div style="text-align:center; padding:16px; font-size:0.85rem; color:#64748B;">لا توجد عناصر بالحافظة تطابق البحث.</div>';
      return;
    }

    let html = '';
    filtered.forEach(clip => {
      html += `
        <div class="clip-card" data-id="${clip.id}">
          <div class="clip-german-row">
            <span class="clip-de">${escapeHtml(clip.text)}</span>
            <div class="clip-actions">
              <button class="btn-icon-sm" onclick="window.speechEngine.speakGerman('${escapeJs(clip.text)}')" title="نطق الكلمة">🔊</button>
              <button class="btn-icon-sm delete" onclick="deleteClip('${clip.id}')" title="حذف من الحافظة">🗑️</button>
            </div>
          </div>
          <div class="clip-ar-row">
            <span>🇪🇬 ${escapeHtml(clip.arabic_meaning)}</span>
            <span style="font-size:0.7rem; background:#F1F5F9; padding:2px 6px; border-radius:4px;">${escapeHtml(clip.label || 'B2')}</span>
          </div>
        </div>
      `;
    });
    vaultList.innerHTML = html;
  }

  vaultFilter.addEventListener('input', (e) => {
    renderVault(e.target.value);
  });

  async function addClipToBackend(clipData) {
    try {
      const res = await fetch('/api/clips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(clipData)
      });
      if (res.ok) {
        showToast('تمت الإضافة إلى الحافظة الدائمة بنجاح 📥');
        await loadClips();
      }
    } catch (e) {
      showToast('تعذر حفظ العنصر بالحافظة.', true);
    }
  }

  window.deleteClip = async (id) => {
    try {
      const res = await fetch(`/api/clips/${id}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('تم الحذف من الحافظة 🗑️');
        await loadClips();
      }
    } catch (e) {
      showToast('فشل حذف العنصر.', true);
    }
  };

  // تصدير واستيراد الملفات
  exportDocxBtn.addEventListener('click', () => {
    window.location.href = '/api/clips/export-docx';
    showToast('جاري تصدير ملف Word (.docx) 📄');
  });

  exportJsonBtn.addEventListener('click', () => {
    window.location.href = '/api/clips/export-json';
    showToast('جاري تصدير ملف JSON 💾');
  });

  importJsonBtn.addEventListener('click', () => {
    importFileInput.click();
  });

  importFileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/clips/import-json', {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`تم استيراد ${data.imported_count} عنصر بنجاح ✓`);
        await loadClips();
      } else {
        showToast('فشل استيراد الملف. تأكد من صحة تنسيق JSON.', true);
      }
    } catch (err) {
      showToast('خطأ أثناء الاستيراد.', true);
    }
    importFileInput.value = '';
  });

  // ==================== نماذج الجمل الجاهزة ====================
  document.querySelectorAll('.chip-sample').forEach(chip => {
    chip.addEventListener('click', (e) => {
      const sample = e.target.getAttribute('data-text');
      textInput.value = sample;
      lockingManager.triggerCommit(sample);
    });
  });

  // مسح السجل المؤقت
  document.getElementById('clearTurnsBtn').addEventListener('click', async () => {
    if (confirm('هل تريد مسح سجل المحادثات المؤقت؟')) {
      try {
        await fetch('/api/turns', { method: 'DELETE' });
        lockedTurnsList.innerHTML = '';
        showToast('تم تفريغ السجل.');
      } catch (e) {}
    }
  });

  // دليل الاستخدام المنبثق
  document.getElementById('openGuideBtn').addEventListener('click', () => {
    guideModal.classList.remove('hidden');
  });
  window.closeGuideModal = () => {
    guideModal.classList.add('hidden');
  };

  // ==================== أدوات مساعدة ====================
  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function escapeJs(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // بدء تشغيل النظام
  checkSystemHealth();
  loadClips();
});
