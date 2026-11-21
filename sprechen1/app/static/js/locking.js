/**
 * locking.js - مدير قفل الجمل والتصحيح الصوتي الذكي (Sentence Locking)
 * يمنع حرق الـ API، يطبق مهلة سكون 650ms أو 12 كلمة أو isFinal،
 * ويثبت الجمل المنتهية دون إعادة رسم كامل الصفحة.
 */

class SentenceLockingManager {
  constructor(options = {}) {
    this.silenceMs = 650;
    this.maxWordsPerChunk = 12;
    this.silenceTimer = null;
    this.isProcessing = false;
    this.activeBuffer = '';
    this.lastProcessedText = '';
    this.lastSentenceContext = '';
    this.apiCallsCount = 0; // لقياس عدد طلبات الـ API وضمان عدم الحرق
    this.committedWordsInSegment = 0;
    this.lockedTurns = [];

    this.onLockTurn = options.onLockTurn || null;
    this.onActiveUpdate = options.onActiveUpdate || null;
    this.onError = options.onError || null;
  }

  // معالجة الكلام اللحظي أثناء التدفق
  feedInterim(interimText) {
    const clean = interimText.trim();
    if (!clean) return;

    if (this.onActiveUpdate) {
      this.onActiveUpdate(clean, false);
    }

    // 1. فحص إذا تجاوز عدد الكلمات الجديدة 12 كلمة في هذا المقطع
    const currentWordCount = clean.split(/\s+/).length;
    const uncommittedWords = currentWordCount - this.committedWordsInSegment;

    if (uncommittedWords >= this.maxWordsPerChunk && !this.isProcessing) {
      this.clearTimer();
      this.committedWordsInSegment = currentWordCount;
      this.triggerCommit(clean);
      return;
    }

    // 2. تجديد مؤقت السكون 650ms
    this.resetSilenceTimer(clean);
  }

  // عند اكتمال مقطع نهائي من محرك الصوت (isFinal = true)
  feedFinal(finalText) {
    this.clearTimer();
    this.committedWordsInSegment = 0;
    const clean = finalText.trim();
    if (clean) {
      this.triggerCommit(clean);
    }
  }

  // عند الكتابة اليدوية بالكيبورد في خانة النص
  feedTyping(text) {
    const clean = text.trim();
    if (this.onActiveUpdate) {
      this.onActiveUpdate(clean, false);
    }

    if (!clean) {
      this.clearTimer();
      return;
    }

    // إذا انتهت الجملة بنقطة أو علامة استفهام فوراً نفذ
    if (/[\.\?\!\n]$/.test(clean)) {
      this.clearTimer();
      this.triggerCommit(clean);
      return;
    }

    // وإلا انتظر سكون 650ms
    this.resetSilenceTimer(clean);
  }

  resetSilenceTimer(text) {
    this.clearTimer();
    this.silenceTimer = setTimeout(() => {
      this.triggerCommit(text);
    }, this.silenceMs);
  }

  clearTimer() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
  }

  // تثبيت وإرسال الجملة للتصحيح وقفلها
  async triggerCommit(rawText) {
    const textToCorrect = rawText.trim();
    if (!textToCorrect || textToCorrect === this.lastProcessedText || this.isProcessing) {
      return;
    }

    this.isProcessing = true;
    this.lastProcessedText = textToCorrect;
    this.apiCallsCount++;

    if (this.onActiveUpdate) {
      this.onActiveUpdate(textToCorrect, true); // حالة جاري المعالجة
    }

    try {
      const response = await fetch('/api/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textToCorrect,
          is_final: true
        })
      });

      if (!response.ok) {
        throw new Error(`خطأ من الخادم (${response.status}): تعذر تدقيق الجملة.`);
      }

      const result = await response.json();
      this.lastSentenceContext = result.corrected_german || '';

      // حفظ الجولة في قاعدة بيانات SQLite بالخلفية
      this.saveTurnToBackend(result);

      // قفل الجملة وتحديث الشاشة الموضعي
      if (this.onLockTurn) {
        this.onLockTurn(result);
      }
    } catch (err) {
      console.error('Correction Error:', err);
      if (this.onError) {
        this.onError(err.message || 'فشل الاتصال بخادم التدقيق. تأكد من عمل السيرفر.');
      }
    } finally {
      this.isProcessing = false;
    }
  }

  async saveTurnToBackend(result) {
    try {
      await fetch('/api/turns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_sentence: result.user_sentence,
          is_correct: result.is_correct,
          corrected_german: result.corrected_german,
          arabic_meaning: result.arabic_meaning,
          why_wrong: result.why_summary,
          replaced_words: result.replaced_words || [],
          radar_rules: result.radar_rules || []
        })
      });
    } catch (e) {
      console.warn('Failed to save turn to SQLite:', e);
    }
  }

  getApiCallCount() {
    return this.apiCallsCount;
  }
}

window.SentenceLockingManager = SentenceLockingManager;
