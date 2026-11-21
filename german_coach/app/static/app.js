/**
 * German Coach - Phase 4B Frontend Controller
 * Complete 6-Section Architecture, SQLite Caching, Word Inspector, Smart Debounce,
 * Persistent Clips & Turns, and Client-Side Word (.docx) Generator.
 */

(function () {
  'use strict';

  // ============================================================================
  // Application State
  // ============================================================================
  const state = {
    level: 'B2',
    tone: localStorage.getItem('coach_tone') || 'du', // 'du' | 'Sie'
    activeSec3Tab: 'direct', // 'direct' | 'native'
    sec4Filter: 'all', // 'all' | 'logic_l1' | 'grammar' | 'style'
    speechRate: 1.0,
    isRecording: false,
    activeMicLang: null, // 'de-DE' | 'ar-EG'
    recognition: null,
    silenceTimer: null,
    silenceDelayMs: 650, // Fast natural micro-pause debounce
    micSilenceAutoStopTimer: null,
    lastSpeechTimestamp: 0,
    typingTimer: null,
    currentAbortController: null,
    currentWordData: null,
    lastCorrection: null,
    lastSubmittedText: '',
    accumulatedSpeech: '',
    lastProcessedLength: 0,
    sessionPassages: [], // Array of { original, originalHtml, corrected, arabic, replacements, radarRules, summaryAr, isCorrect }
    sessionSentences: 0,
    sessionErrors: 0,
    sessionCorrect: 0,
    isTtsSpeaking: false,
    autoCorrectEnabled: true,
    continuousMicEnabled: true,
    autoTtsEnabled: false, // Default OFF: do NOT read text automatically
    autoSaveTurnEnabled: false,
    deletedTurnsCache: [],
    clipsCount: 0,
    micRestartTimer: null,
    audioContext: null,
    audioAnalyser: null,
    audioStream: null,
    audioAnimFrame: null,
  };

  // ============================================================================
  // DOM Elements
  // ============================================================================
  const levelSelect = document.getElementById('level-select');
  const toneSelect = document.getElementById('tone-select');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const latencyIndicator = document.getElementById('latency-indicator');
  const cacheIndicatorBadge = document.getElementById('cache-indicator-badge');
  const clipsCountBadge = document.getElementById('clips-count-badge');
  const micNotice = document.getElementById('mic-notice');
  const micNoticeClose = document.getElementById('mic-notice-close');

  // Section 1
  const mainInput = document.getElementById('main-input');
  const btnMicDe = document.getElementById('btn-mic-de');
  const btnMicAr = document.getElementById('btn-mic-ar');
  const btnMicStop = document.getElementById('btn-mic-stop');
  const micStateLabel = document.getElementById('mic-state-label');
  const btnDiagMic = document.getElementById('btn-diag-mic');
  const micVolumeMeter = document.getElementById('mic-volume-meter');
  const micVolumeBar = document.getElementById('mic-volume-bar');
  const btnClearInput = document.getElementById('btn-clear-input');
  const btnCopyInput = document.getElementById('btn-copy-input');
  const btnSaveAsTurn = document.getElementById('btn-save-as-turn');
  const btnSubmitCorrect = document.getElementById('btn-submit-correct');
  const spinnerCorrect = document.getElementById('spinner-correct');

  // Section 1 Live Automation Elements
  const btnToggleAutoCorrect = document.getElementById('btn-toggle-auto-correct');
  const btnToggleContinuousMic = document.getElementById('btn-toggle-continuous-mic');
  const btnToggleAutoTts = document.getElementById('btn-toggle-auto-tts');
  const btnStopSpeech = document.getElementById('btn-stop-speech');
  const labelAutoCorrect = document.getElementById('label-auto-correct');
  const labelContinuousMic = document.getElementById('label-continuous-mic');
  const labelAutoTts = document.getElementById('label-auto-tts');
  const liveAutoStatus = document.getElementById('live-auto-status');

  // Live Session Statistics Bar
  const statTotalSentences = document.getElementById('stat-total-sentences');
  const statTotalErrors = document.getElementById('stat-total-errors');
  const statCorrectSentences = document.getElementById('stat-correct-sentences');

  // Section 2
  const originalDiffBox = document.getElementById('original-diff-box');
  const summaryArBox = document.getElementById('summary-ar-box');
  const summaryArText = document.getElementById('summary-ar-text');
  const btnCopyOriginal = document.getElementById('btn-copy-original');

  // Section 3
  const tabBtnDirect = document.getElementById('tab-btn-direct');
  const tabBtnNative = document.getElementById('tab-btn-native');
  const wordInspector = document.getElementById('word-inspector');
  const inspWordDe = document.getElementById('insp-word-de');
  const inspWordAr = document.getElementById('insp-word-ar');
  const btnInspSpeak = document.getElementById('btn-insp-speak');
  const btnInspSaveClip = document.getElementById('btn-insp-save-clip');
  const btnInspCopy = document.getElementById('btn-insp-copy');
  const correctedHeroBox = document.getElementById('corrected-hero-box');
  const sentenceArabicMeaning = document.getElementById('sentence-arabic-meaning');
  const btnSpeakCorrected = document.getElementById('btn-speak-corrected');
  const btnCopyGerman = document.getElementById('btn-copy-german');
  const btnCopyArabic = document.getElementById('btn-copy-arabic');
  const btnClipCorrected = document.getElementById('btn-clip-corrected');
  const btnTtsToggleRate = document.getElementById('btn-tts-toggle-rate');
  const turnsList = document.getElementById('turns-list');
  const btnRefreshTurns = document.getElementById('btn-refresh-turns');
  const selectionPopup = document.getElementById('selection-popup');
  const selBtnCopy = document.getElementById('sel-btn-copy');
  const selBtnClip = document.getElementById('sel-btn-clip');
  const selBtnSpeak = document.getElementById('sel-btn-speak');
  const selBtnAsk = document.getElementById('sel-btn-ask');

  // Assistant in Section 3
  const assistantQuestionInput = document.getElementById('assistant-question-input');
  const btnAssistantSend = document.getElementById('btn-assistant-send');
  const assistantChatList = document.getElementById('assistant-chat-list');

  // Section 4
  const replacementsContainer = document.getElementById('replacements-container');
  const sec4FilterChips = document.querySelectorAll('.sec4-filter-bar .btn-filter-chip');

  // Section 5
  const radarRulesContainer = document.getElementById('radar-rules-container');
  const radarStatsBars = document.getElementById('radar-stats-bars');
  const btnRefreshRadar = document.getElementById('btn-refresh-radar');

  // Section 6
  const clipsListContainer = document.getElementById('clips-list-container');
  const btnAddClipManual = document.getElementById('btn-add-clip-manual');
  const btnPasteExplainClip = document.getElementById('btn-paste-explain-clip');
  const btnExportClipsDocx = document.getElementById('btn-export-clips-docx');
  const btnExportClipsJson = document.getElementById('btn-export-clips-json');
  const btnImportClipsJson = document.getElementById('btn-import-clips-json');
  const importJsonFileInput = document.getElementById('import-json-file-input');
  const btnClearAllClips = document.getElementById('btn-clear-all-clips');

  // Top Nav Actions
  const btnExportWord = document.getElementById('btn-export-word');
  const btnClearTurns = document.getElementById('btn-clear-turns');
  const btnTelegramBackup = document.getElementById('btn-telegram-backup');
  const btnOpenHelp = document.getElementById('btn-open-help');
  const btnCloseHelp = document.getElementById('btn-close-help');
  const helpModal = document.getElementById('help-modal');

  // Toast
  const toastBox = document.getElementById('toast-box');
  const toastMessage = document.getElementById('toast-message');
  const toastUndoBtn = document.getElementById('toast-undo-btn');

  // ============================================================================
  // Helpers: Toast Notification & HTML Escape
  // ============================================================================
  let toastTimer = null;
  function showToast(message, duration = 3500, onUndo = null) {
    if (!toastBox) return;
    clearTimeout(toastTimer);
    toastMessage.textContent = message;

    if (onUndo) {
      toastUndoBtn.style.display = 'inline-block';
      toastUndoBtn.onclick = () => {
        onUndo();
        toastBox.classList.remove('show');
      };
    } else {
      toastUndoBtn.style.display = 'none';
      toastUndoBtn.onclick = null;
    }

    toastBox.classList.add('show');
    toastTimer = setTimeout(() => {
      toastBox.classList.remove('show');
    }, duration);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function copyToClipboard(text, successMsg = 'تم النسخ للحافظة 📋') {
    if (!text) return;
    navigator.clipboard.writeText(text).then(
      () => showToast(successMsg, 2000),
      () => showToast('تعذر النسخ التلقائي.', 2000)
    );
  }

  // ============================================================================
  // Server Health & Status
  // ============================================================================
  async function checkServerHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        statusDot.style.background = '#10B981';
        statusText.textContent = 'متصل بـ SQLite على السيرفر';
      } else {
        throw new Error('Server degraded');
      }
    } catch {
      statusDot.style.background = '#EF4444';
      statusText.textContent = 'غير متصل بالسيرفر';
    }
  }

  // ============================================================================
  // Browser Speech Synthesis (TTS) & Coordinated Audio
  // ============================================================================
  function getGermanVoice() {
    if (!('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    return (
      voices.find((v) => v.lang === 'de-DE' || v.lang === 'de_DE') ||
      voices.find((v) => v.lang.startsWith('de')) ||
      null
    );
  }

  function stopSpeaking() {
    if ('speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (err) {
        console.warn('speechSynthesis cancel error:', err);
      }
    }
    state.isTtsSpeaking = false;
    if (btnSpeakCorrected) {
      btnSpeakCorrected.innerHTML = '<span>🔊</span><span>استمع للقطعة</span>';
    }
  }

  function speakGerman(text, onDone = null) {
    if (!('speechSynthesis' in window) || !text) {
      if (onDone) onDone();
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'de-DE';
      utterance.rate = state.speechRate;
      const voice = getGermanVoice();
      if (voice) utterance.voice = voice;

      state.isTtsSpeaking = true;

      // Coordinate with SpeechRecognition to prevent the mic from hearing the TTS speaker
      if (state.recognition && state.isRecording) {
        try {
          state.recognition.abort();
        } catch {}
      }

      const finishTts = () => {
        state.isTtsSpeaking = false;
        // Resume continuous listening seamlessly if still recording
        if (state.isRecording && state.continuousMicEnabled && state.recognition) {
          try {
            state.recognition.start();
          } catch {}
        }
        if (onDone) onDone();
      };

      utterance.onend = finishTts;
      utterance.onerror = finishTts;

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      state.isTtsSpeaking = false;
      console.warn('SpeechSynthesis error:', e);
      if (onDone) onDone();
    }
  }

  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => getGermanVoice();
  }

  // ============================================================================
  // Web Speech API & Live Audio Input Engine (Resilient & Self-Healing)
  // ============================================================================
  function updateLiveStatus(text) {
    if (liveAutoStatus) {
      liveAutoStatus.textContent = text;
    }
  }

  // Live Audio Level Visualizer via Web Audio API (Provides instant proof that mic hears sound)
  async function startAudioLevelMonitor() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.audioStream = stream;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      state.audioContext = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);
      state.audioAnalyser = analyser;

      if (micVolumeMeter) micVolumeMeter.style.display = 'inline-block';

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      function checkVolume() {
        if (!state.isRecording) {
          stopAudioLevelMonitor();
          return;
        }
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
        const avg = sum / dataArray.length;
        const percent = Math.min(100, Math.round((avg / 128) * 100));
        if (micVolumeBar) {
          micVolumeBar.style.width = `${percent}%`;
          if (percent > 12) {
            micVolumeBar.style.background = '#10B981'; // Green: active voice detected
          } else {
            micVolumeBar.style.background = '#F59E0B'; // Amber: silence / quiet
          }
        }
        state.audioAnimFrame = requestAnimationFrame(checkVolume);
      }
      checkVolume();
    } catch (err) {
      console.warn('Audio level monitor error (non-fatal):', err);
    }
  }

  function stopAudioLevelMonitor() {
    if (state.audioAnimFrame) {
      cancelAnimationFrame(state.audioAnimFrame);
      state.audioAnimFrame = null;
    }
    if (state.audioStream) {
      state.audioStream.getTracks().forEach((t) => t.stop());
      state.audioStream = null;
    }
    if (state.audioContext && state.audioContext.state !== 'closed') {
      state.audioContext.close().catch(() => {});
      state.audioContext = null;
    }
    if (micVolumeMeter) micVolumeMeter.style.display = 'none';
    if (micVolumeBar) micVolumeBar.style.width = '0%';
  }

  // 30-Second Inactivity Auto-Stop Timer
  function resetMicSilenceTimer() {
    clearTimeout(state.micSilenceAutoStopTimer);
    if (!state.isRecording) return;

    state.lastSpeechTimestamp = Date.now();
    state.micSilenceAutoStopTimer = setTimeout(() => {
      if (state.isRecording) {
        console.info('Auto-stopping mic after 30 seconds of silence.');
        stopRecording();
        updateLiveStatus('⏹️ تم إيقاف المايك تلقائياً لتوفير الطاقة بعد 30 ثانية من الصمت.');
        showToast('⏹️ تم إيقاف المايك تلقائياً بعد 30 ثانية من الصمت.', 4000);
      }
    }, 30000);
  }

  function clearMicSilenceTimer() {
    clearTimeout(state.micSilenceAutoStopTimer);
    state.micSilenceAutoStopTimer = null;
  }

  // Create a clean, isolated SpeechRecognition session
  function createSpeechRecognition(langCode) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const isSecure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';

    if (!SpeechRecognition || !isSecure) {
      if (micNotice) micNotice.style.display = 'flex';
      if (!isSecure) {
        if (confirm('🎙️ لتشغيل المايك الصوتي المباشر، يشترط المتصفح الاتصال المشفر (HTTPS).\n\nهل ترغب بالانتقال فوراً للرابط الآمن المشفر لتفعيل المايك؟')) {
          if (window.top && window.top !== window) {
            window.top.location.href = 'https://deutsch.srv2162066.hstgr.cloud/';
          } else {
            window.location.href = 'https://deutsch.srv2162066.hstgr.cloud/coach/';
          }
        }
      } else {
        showToast('⚠️ المتصفح لا يدعم التعرف الصوتي المباشر. يرجى استخدام Google Chrome أو Edge.', 4000);
      }
      return null;
    }

    try {
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.lang = langCode;

      rec.onstart = () => {
        state.isRecording = true;
        state.activeMicLang = langCode;
        resetMicSilenceTimer();
        if (btnMicStop) btnMicStop.classList.add('recording-active');
        if (langCode === 'de-DE') {
          btnMicDe.classList.add('active-recording');
          btnMicAr.classList.remove('active-recording');
          micStateLabel.textContent = '🇩🇪 المايك نشط بالألماني (تحدث الآن)...';
        } else {
          btnMicAr.classList.add('active-recording');
          btnMicDe.classList.remove('active-recording');
          micStateLabel.textContent = '🇪🇬 المايك نشط بالعربي (تحدث الآن)...';
        }
        updateLiveStatus('🎙️ المايك متصل ويستمع الآن...');
      };

      rec.onaudiostart = () => {
        resetMicSilenceTimer();
        updateLiveStatus('🎙️ تم فتح قناة الصوت في المايك...');
      };

      rec.onspeechstart = () => {
        resetMicSilenceTimer();
        updateLiveStatus('🗣️ تم التقاط صوت كلام...');
      };

      rec.onresult = (event) => {
        if (state.isTtsSpeaking) return;
        resetMicSilenceTimer();

        let finalChunk = '';
        let interimChunk = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const item = event.results[i];
          const text = item[0].transcript;
          if (item.isFinal) {
            finalChunk += text;
          } else {
            interimChunk += text;
          }
        }

        // Accumulate finalized speech segments
        if (finalChunk.trim()) {
          state.accumulatedSpeech = (state.accumulatedSpeech ? state.accumulatedSpeech + ' ' : '') + finalChunk.trim();
        }

        const currentDisplay = (state.accumulatedSpeech ? state.accumulatedSpeech + ' ' : '') + interimChunk;
        mainInput.value = currentDisplay.trim();

        if (interimChunk) {
          updateLiveStatus(`🎙️ جاري الاستماع: ${interimChunk.slice(0, 30)}...`);
        } else {
          updateLiveStatus('⚡ جاهز للتصحيح التلقائي');
        }

        if (!state.autoCorrectEnabled) return;

        // 1. Immediate trigger on finalized sentence (isFinal)
        if (finalChunk.trim()) {
          const textToSubmit = state.accumulatedSpeech.trim() || finalChunk.trim();
          if (textToSubmit && textToSubmit !== state.lastSubmittedText && textToSubmit.length >= 2) {
            clearTimeout(state.silenceTimer);
            state.silenceTimer = setTimeout(() => {
              submitCorrection(true, true);
            }, 250);
            return;
          }
        }

        // 2. Fast natural micro-pause debounce during continuous speech
        clearTimeout(state.silenceTimer);
        state.silenceTimer = setTimeout(() => {
          const textToSubmit = mainInput.value.trim();
          if (textToSubmit && textToSubmit.length >= 3 && textToSubmit !== state.lastSubmittedText) {
            submitCorrection(true, true);
          }
        }, state.silenceDelayMs);
      };

      rec.onerror = (e) => {
        console.warn('Speech recognition error:', e.error);
        if (e.error === 'not-allowed') {
          showToast('❌ تم حظر الميكروفون! اضغط على علامة القفل بجوار الرابط في المتصفح واسمح بالمايك.', 4500);
          micStateLabel.textContent = '❌ إذن المايك محظور بالمتصفح';
          stopRecording();
        } else if (e.error === 'network') {
          showToast('⚠️ انقطع اتصال خدمة التعرف الصوتي (Google Speech Network). جاري إعادة الربط...', 3500);
          updateLiveStatus('⚠️ خطأ شبكة في سيرفر الصوت، جاري إعادة المحاولة...');
        } else if (e.error === 'audio-capture') {
          showToast('❌ لم يتم العثور على ميكروفون، أو المايك مشغول في تطبيق آخر.', 4000);
          micStateLabel.textContent = '❌ تعذر الوصول لعتاد المايك';
          stopRecording();
        } else if (e.error === 'no-speech') {
          // Normal pause in natural speech
        }
      };

      rec.onend = () => {
        // Stop if 30 seconds of silence elapsed
        if (state.lastSpeechTimestamp > 0 && Date.now() - state.lastSpeechTimestamp >= 30000) {
          stopRecording();
          updateLiveStatus('⏹️ تم إيقاف المايك تلقائياً بعد 30 ثانية من الصمت.');
          return;
        }

        // Continuous listening auto-restart with a clean fresh instance
        if (state.isRecording && state.continuousMicEnabled && !state.isTtsSpeaking) {
          clearTimeout(state.micRestartTimer);
          state.micRestartTimer = setTimeout(() => {
            if (state.isRecording && !state.isTtsSpeaking) {
              startRecordingSession(state.activeMicLang);
            }
          }, 200);
        } else if (!state.isRecording) {
          stopRecordingUI();
          stopAudioLevelMonitor();
        }
      };

      return rec;
    } catch (err) {
      console.warn('Failed to instantiate SpeechRecognition:', err);
      return null;
    }
  }

  function startRecordingSession(langCode) {
    if (!langCode) return;
    // Clean up previous instance cleanly
    if (state.recognition) {
      try {
        state.recognition.onstart = null;
        state.recognition.onend = null;
        state.recognition.onerror = null;
        state.recognition.onresult = null;
        state.recognition.abort();
      } catch {}
      state.recognition = null;
    }

    const rec = createSpeechRecognition(langCode);
    if (!rec) return;

    state.recognition = rec;
    try {
      rec.start();
    } catch (e) {
      console.warn('Recognition start error:', e);
      setTimeout(() => {
        if (state.isRecording && state.recognition) {
          try { state.recognition.start(); } catch {}
        }
      }, 300);
    }
  }

  function startRecording(langCode) {
    stopSpeaking(); // Immediately stop any voice reading when starting recording

    // Clicking the active mic toggles it off
    if (state.isRecording && state.activeMicLang === langCode) {
      stopRecording();
      return;
    }

    // Keep existing text in textarea so speech appends continuously
    state.accumulatedSpeech = mainInput.value.trim();
    state.lastProcessedLength = state.accumulatedSpeech.length;
    state.activeMicLang = langCode;
    state.isRecording = true;

    startRecordingSession(langCode);
    startAudioLevelMonitor();
  }

  function stopRecording() {
    state.isRecording = false;
    state.activeMicLang = null;
    clearMicSilenceTimer();
    clearTimeout(state.silenceTimer);
    clearTimeout(state.micRestartTimer);
    stopSpeaking();
    stopRecordingUI();
    stopAudioLevelMonitor();

    if (state.recognition) {
      try {
        state.recognition.onend = null;
        state.recognition.stop();
      } catch {}
      state.recognition = null;
    }
  }

  function stopRecordingUI() {
    btnMicDe.classList.remove('active-recording');
    btnMicAr.classList.remove('active-recording');
    if (btnMicStop) btnMicStop.classList.remove('recording-active');
    micStateLabel.textContent = 'جاهز للاستماع';
    updateLiveStatus('⚡ التصحيح التلقائي الفوري نشط');
    if (micVolumeMeter) micVolumeMeter.style.display = 'none';
  }

  // Automated 4-Point Mic Diagnostic Tool
  async function runMicDiagnostic() {
    showToast('🔍 جاري فحص الميكروفون وصلاحيات المتصفح... ⏳', 2500);

    const isSecure = window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    const hasSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

    let micAccessGranted = false;
    let micPeakVolume = 0;
    let micErrorMsg = '';

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        micAccessGranted = true;
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          const ctx = new AudioCtx();
          const source = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 64;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          // Sample volume for 1.5 seconds
          const t0 = Date.now();
          while (Date.now() - t0 < 1500) {
            analyser.getByteFrequencyData(dataArray);
            for (let v of dataArray) {
              if (v > micPeakVolume) micPeakVolume = v;
            }
            await new Promise((r) => setTimeout(r, 80));
          }
          ctx.close().catch(() => {});
        }
        stream.getTracks().forEach((t) => t.stop());
      } catch (err) {
        micAccessGranted = false;
        micErrorMsg = err.name || err.message;
      }
    }

    const volumePercent = Math.min(100, Math.round((micPeakVolume / 128) * 100));

    let report = `نتيجة فحص المايك 🎙️:\n\n`;
    report += `١. اتصال HTTPS آمن: ${isSecure ? '✅ سليم' : '❌ غير مؤمن'}\n`;
    report += `٢. دعم التعرف الصوتي بالمتصفح: ${hasSpeech ? '✅ مدعوم (Web Speech API)' : '❌ غير مدعوم (يرجى استخدام Google Chrome أو Edge)'}\n`;
    report += `٣. إذن وصول المايك: ${micAccessGranted ? '✅ مسموح به' : `❌ مرفوض أو محظور (${micErrorMsg})`}\n`;
    report += `٤. التقاط ترددات الصوت: ${micAccessGranted ? (volumePercent > 5 ? `✅ تم رصد صوت بنسبة (${volumePercent}%)` : `⚠️ لم يتم رصد أي صوت (${volumePercent}%). تأكد من عدم كتم المايك في نظامك`) : '—'}\n\n`;

    if (isSecure && hasSpeech && micAccessGranted) {
      report += `الخلاصة: المايك سليم تماماً وجاهز للاستخدام!`;
    } else if (!micAccessGranted) {
      report += `الحل: اضغط على أيقونة القفل أو الإعدادات بجوار رابط الموقع أعلى المتصفح، وغير الميكروفون إلى "السماح" (Allow).`;
    }

    alert(report);
  }

  // Live Session Statistics Helper
  function updateSessionStatsUI() {
    if (statTotalSentences) statTotalSentences.textContent = state.sessionSentences;
    if (statTotalErrors) statTotalErrors.textContent = state.sessionErrors;
    if (statCorrectSentences) statCorrectSentences.textContent = state.sessionCorrect;
  }

  // Helpers to get full passage text across sentences
  function getFullOriginalText() {
    if (state.sessionPassages.length === 0) return mainInput.value.trim();
    return state.sessionPassages.map((p) => p.original).join(' ');
  }

  function getFullCorrectedGerman() {
    const isNative = state.activeSec3Tab === 'native';
    if (state.sessionPassages.length === 0) {
      if (!state.lastCorrection) return '';
      return isNative
        ? (state.lastCorrection.native_version || state.lastCorrection.corrected_text || '')
        : (state.lastCorrection.direct_correction || state.lastCorrection.corrected_text || '');
    }
    return state.sessionPassages
      .map((p) => (isNative ? (p.native || p.corrected) : (p.direct || p.corrected)))
      .join(' ');
  }

  function getFullArabicTranslation() {
    const isNative = state.activeSec3Tab === 'native';
    if (state.sessionPassages.length === 0) {
      if (!state.lastCorrection) return '';
      return isNative
        ? (state.lastCorrection.native_arabic_meaning || state.lastCorrection.arabic_meaning || '')
        : (state.lastCorrection.direct_arabic_meaning || state.lastCorrection.arabic_meaning || '');
    }
    return state.sessionPassages
      .map((p) => (isNative ? (p.nativeArabic || p.arabic) : (p.directArabic || p.arabic)))
      .filter(Boolean)
      .join(' ');
  }

  // ============================================================================
  // Section 1 & 2 & 3: Sentence Correction & Analysis (/api/correct)
  // ============================================================================
  async function submitCorrection(isAuto = false, isFromSpeech = false) {
    const fullText = mainInput.value.trim();
    if (!fullText) {
      if (!isAuto) showToast('يرجى كتابة أو نطق جملة أولاً.', 2000);
      return;
    }

    let textToSubmit = '';

    if (isFromSpeech) {
      // Natural speech pause / breath: extract newly spoken segment since last processed index
      if (state.lastProcessedLength > fullText.length) {
        state.lastProcessedLength = 0;
      }
      const delta = fullText.slice(state.lastProcessedLength).trim();
      textToSubmit = delta || fullText;
      if (!textToSubmit || textToSubmit.length < 2) {
        return;
      }
      if (textToSubmit === state.lastSubmittedText) {
        return;
      }
    } else {
      // Check if user has highlighted text in the input
      const selStart = mainInput.selectionStart;
      const selEnd = mainInput.selectionEnd;
      if (selStart !== undefined && selEnd !== undefined && selEnd > selStart) {
        const selected = mainInput.value.substring(selStart, selEnd).trim();
        if (selected.length >= 2) {
          textToSubmit = selected;
        }
      }

      if (!textToSubmit) {
        if (state.lastProcessedLength > fullText.length) {
          state.lastProcessedLength = 0;
        }
        const delta = fullText.slice(state.lastProcessedLength).trim();
        if (isAuto && fullText === state.lastSubmittedText) {
          return;
        }
        if (delta && delta.length >= 2) {
          textToSubmit = delta;
        } else {
          // Re-process full text: reset passage accumulation
          textToSubmit = fullText;
          state.sessionPassages = [];
          state.sessionSentences = 0;
          state.sessionErrors = 0;
          state.sessionCorrect = 0;
        }
      }
    }

    // Cancel any in-flight request to ensure latest text wins
    if (state.currentAbortController) {
      state.currentAbortController.abort();
    }
    state.currentAbortController = new AbortController();

    state.lastSubmittedText = textToSubmit;
    state.lastProcessedLength = fullText.length;

    btnSubmitCorrect.disabled = true;
    spinnerCorrect.style.display = 'inline-block';
    updateLiveStatus('⏳ جاري التحليل والتصحيح التلقائي...');

    try {
      const response = await fetch('/api/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textToSubmit,
          level: state.level,
          tone: state.tone,
        }),
        signal: state.currentAbortController.signal,
      });

      if (!response.ok) {
        const errJson = await response.json();
        throw new Error(errJson.detail || 'حدث خطأ أثناء معالجة الجملة.');
      }

      const result = await response.json();
      state.lastCorrection = result;

      // Update latency indicator
      latencyIndicator.textContent = `${result.elapsed_ms || 0} ms`;
      if (result.cached) {
        cacheIndicatorBadge.style.display = 'inline-block';
        cacheIndicatorBadge.textContent = 'كاش SQLite ⚡';
      } else {
        cacheIndicatorBadge.style.display = 'inline-block';
        cacheIndicatorBadge.textContent = 'توليد حي ✨';
      }

      // Format original text with 3-color highlights for mistakes
      const original = result.original_text || textToSubmit;
      const errors = result.errors || result.replacements || [];
      const replacements = result.replacements || result.errors || [];
      const passageIdx = state.sessionPassages.length;

      // Assign unique errId to each error in this passage
      const taggedErrors = errors.map((err, eIdx) => ({
        ...err,
        errId: `err-${passageIdx}-${eIdx}`,
      }));

      // Render 3-color in-text spans
      let originalHtml = escapeHtml(original);
      if (!result.is_correct && taggedErrors.length > 0) {
        const spansToMark = [];
        taggedErrors.forEach((err) => {
          const wrong = (err.original || err.wrong || '').trim();
          if (!wrong) return;
          const cat = err.category || 'grammar';
          const strikeClass = cat === 'logic_l1' ? 'strike-logic' : (cat === 'style' ? 'strike-style' : 'strike-grammar');

          let pos = 0;
          while (pos < original.length) {
            const idx = original.toLowerCase().indexOf(wrong.toLowerCase(), pos);
            if (idx === -1) break;
            spansToMark.push({
              start: idx,
              end: idx + wrong.length,
              wrongText: original.slice(idx, idx + wrong.length),
              strikeClass: strikeClass,
              errId: err.errId,
              cat: cat,
            });
            pos = idx + wrong.length;
          }
        });

        // Sort spans by start index, filter out overlapping
        spansToMark.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
        const filteredSpans = [];
        let lastEnd = 0;
        spansToMark.forEach((s) => {
          if (s.start >= lastEnd) {
            filteredSpans.push(s);
            lastEnd = s.end;
          }
        });

        // Reconstruct originalHtml with colored strike spans
        if (filteredSpans.length > 0) {
          let cursor = 0;
          let builtHtml = '';
          filteredSpans.forEach((s) => {
            if (s.start > cursor) {
              builtHtml += escapeHtml(original.slice(cursor, s.start));
            }
            const catTitle = s.cat === 'logic_l1' ? 'منطق وفخ عربي' : (s.cat === 'style' ? 'أسلوب وتكرار' : 'قواعد ونحو');
            builtHtml += `<span class="strike-wrong ${s.strikeClass}" title="${catTitle}">${escapeHtml(s.wrongText)}</span>`;
            cursor = s.end;
          });
          if (cursor < original.length) {
            builtHtml += escapeHtml(original.slice(cursor));
          }
          originalHtml = builtHtml;
        }
      }

      // Append to the continuous passage (قطعة متصلة)
      state.sessionPassages.push({
        original: original,
        originalHtml: originalHtml,
        direct: result.direct_correction || result.corrected_text || original,
        native: result.native_version || result.corrected_text || original,
        corrected: result.direct_correction || result.corrected_text || original,
        directArabic: result.direct_arabic_meaning || result.arabic_meaning || '',
        nativeArabic: result.native_arabic_meaning || result.arabic_meaning || '',
        arabic: result.direct_arabic_meaning || result.arabic_meaning || '',
        errors: taggedErrors,
        replacements: replacements,
        radarRules: result.radar_rules || [],
        summaryAr: result.summary_ar || '',
        isCorrect: !!result.is_correct,
      });

      // Update session statistics strictly matching real error cards
      state.sessionSentences++;
      const realErrCount = taggedErrors.length;
      if (result.is_correct || realErrCount === 0) {
        state.sessionCorrect++;
      } else {
        state.sessionErrors += realErrCount;
      }
      updateSessionStatsUI();

      // Render sections as a continuous unified passage (قطعة)
      renderSection2();
      renderSection3();
      renderSection4();
      renderSection5();

      // Auto TTS if enabled
      const textToSpeak = state.activeSec3Tab === 'native'
        ? (result.native_version || result.corrected_text)
        : (result.direct_correction || result.corrected_text);

      if (textToSpeak && state.autoTtsEnabled) {
        speakGerman(textToSpeak);
      }

      updateLiveStatus(result.cached ? '⚡ تم التصحيح الفوري (كاش)' : '✅ تم التصحيح والتحليل بنجاح');
      showToast(result.cached ? '⚡ استجابة فورية من كاش SQLite' : '✅ تم التصحيح والتحليل بنجاح', 2000);

    } catch (err) {
      if (err.name === 'AbortError') return; // Cancelled silently
      showToast(`❌ ${err.message}`, 4000);
      updateLiveStatus('⚠️ تعذر التصحيح التلقائي');
    } finally {
      btnSubmitCorrect.disabled = false;
      spinnerCorrect.style.display = 'none';
      state.currentAbortController = null;
    }
  }

  // Auto-save turn directly to SQLite
  async function autoSaveTurnDirect(result) {
    if (!result) return;
    try {
      const userSentence = result.original_text || mainInput.value.trim();
      const corrected = result.corrected_text || userSentence;
      if (!userSentence && !corrected) return;

      const res = await fetch('/api/turns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_sentence: userSentence,
          corrected_german: corrected,
          arabic_meaning: result.arabic_meaning || '',
          is_correct: !!result.is_correct,
          summary_ar: result.summary_ar || '',
        }),
      });
      if (res.ok) {
        loadTurns();
      }
    } catch (e) {
      console.warn('Auto save turn error:', e);
    }
  }

  // Render Section 2: Text Before Correction (Unified Passage - قطعة متصلة)
  function renderSection2() {
    if (!originalDiffBox) return;

    if (state.sessionPassages.length === 0) {
      originalDiffBox.innerHTML = '<span style="color: #9CA3AF;">النص الأصلي مع التظليل المشطوب على مواضع الخلل النحوي والسياقي سيظهر هنا كقطعة متصلة...</span>';
      if (summaryArBox) summaryArBox.style.display = 'none';
      return;
    }

    // Join all original sentences into one continuous paragraph (قطعة)
    const passageHtml = state.sessionPassages
      .map((p) => p.originalHtml)
      .join(' ');

    originalDiffBox.innerHTML = passageHtml;

    // Collect summaries
    const summaries = state.sessionPassages
      .map((p) => p.summaryAr)
      .filter(Boolean);

    if (summaries.length > 0 && summaryArBox && summaryArText) {
      summaryArBox.style.display = 'flex';
      const unique = [...new Set(summaries)];
      summaryArText.textContent = unique.join(' | ');
    } else if (summaryArBox) {
      summaryArBox.style.display = 'none';
    }
  }

  // Render Section 3: Correct German Text (Unified Passage - قطعة متصلة with Clickable Words & Highlighter on Corrections)
  function renderSection3() {
    if (!correctedHeroBox) return;

    if (state.sessionPassages.length === 0) {
      correctedHeroBox.innerHTML = `
        <span style="color: #6EE7B7;">القطعة الألمانية المصححة ستظهر هنا (كل كلمة قابلة للضغط للاستماع ومعرفة المعنى)...</span>
        <div id="sentence-arabic-meaning" class="sentence-translation-sub" style="display: none;"></div>
      `;
      return;
    }

    const isNativeTab = state.activeSec3Tab === 'native';
    let fullHtml = '';

    state.sessionPassages.forEach((p) => {
      const activeGermanText = isNativeTab ? (p.native || p.corrected || '') : (p.direct || p.corrected || '');
      const replacements = p.replacements || [];

      if (isNativeTab) {
        // Native tab: Clean natural formulation with clickable words for lookup
        const tokenRegex = /[\w\u00C0-\u017F]+|[^\w\s\u00C0-\u017F]+|\s+/g;
        let match;
        let passageHtml = '';
        while ((match = tokenRegex.exec(activeGermanText)) !== null) {
          const token = match[0];
          const isWord = /^[\w\u00C0-\u017F]+$/.test(token);
          if (isWord) {
            passageHtml += `<span class="clickable-word" data-word="${escapeHtml(token)}">${escapeHtml(token)}</span>`;
          } else {
            passageHtml += escapeHtml(token);
          }
        }
        if (fullHtml) fullHtml += ' ';
        fullHtml += passageHtml;
      } else {
        // Direct tab: Highlight replacements with yellow continuous highlighter
        const spans = [];
        replacements.forEach((rep) => {
          const rawRight = (rep.right || rep.correction || '').trim();
          const rawWrong = (rep.wrong || rep.original || '').trim();
          const cleanRight = rawRight.replace(/^[^\w\u00C0-\u017F]+|[^\w\u00C0-\u017F]+$/g, '');
          const tooltip = rawWrong ? `تصحيح: "${rawRight}" بدلاً من "${rawWrong}"` : `تصحيح: "${rawRight}"`;

          let foundPhrase = false;
          if (cleanRight) {
            let pos = 0;
            while (pos < activeGermanText.length) {
              const idx = activeGermanText.toLowerCase().indexOf(cleanRight.toLowerCase(), pos);
              if (idx === -1) break;
              foundPhrase = true;
              spans.push({
                start: idx,
                end: idx + cleanRight.length,
                wrong: rawWrong,
                right: rawRight,
                why: rep.why || rep.explanation_ar || '',
                tooltip: tooltip,
              });
              pos = idx + cleanRight.length;
            }
          }

          if (!foundPhrase && cleanRight) {
            const rightWords = cleanRight.match(/[\w\u00C0-\u017F]+/g) || [];
            const wrongWords = new Set((rawWrong.match(/[\w\u00C0-\u017F]+/g) || []).map((w) => w.toLowerCase()));

            rightWords.forEach((w) => {
              if (!wrongWords.has(w.toLowerCase()) || rightWords.length === 1) {
                let pos = 0;
                while (pos < activeGermanText.length) {
                  const idx = activeGermanText.toLowerCase().indexOf(w.toLowerCase(), pos);
                  if (idx === -1) break;
                  const before = idx === 0 ? ' ' : activeGermanText[idx - 1];
                  const after = idx + w.length >= activeGermanText.length ? ' ' : activeGermanText[idx + w.length];
                  if (!/[\w\u00C0-\u017F]/.test(before) && !/[\w\u00C0-\u017F]/.test(after)) {
                    spans.push({
                      start: idx,
                      end: idx + w.length,
                      wrong: rawWrong,
                      right: rawRight,
                      why: rep.why || rep.explanation_ar || '',
                      tooltip: tooltip,
                    });
                  }
                  pos = idx + w.length;
                }
              }
            });
          }
        });

        const tokenRegex = /[\w\u00C0-\u017F]+|[^\w\s\u00C0-\u017F]+|\s+/g;
        let match;
        let passageHtml = '';

        while ((match = tokenRegex.exec(activeGermanText)) !== null) {
          const token = match[0];
          const start = match.index;
          const end = start + token.length;

          const isWord = /^[\w\u00C0-\u017F]+$/.test(token);
          const matchedSpan = spans.find((s) => s.start <= start && end <= s.end);

          if (matchedSpan) {
            if (isWord) {
              const tooltip = matchedSpan.tooltip || 'تم تصحيح هذه الكلمة';
              passageHtml += `<span class="clickable-word diff-corrected-highlight" data-word="${escapeHtml(token)}" title="${escapeHtml(tooltip)}">${escapeHtml(token)}</span>`;
            } else {
              passageHtml += `<span class="diff-highlight-connector">${escapeHtml(token)}</span>`;
            }
          } else {
            if (isWord) {
              passageHtml += `<span class="clickable-word" data-word="${escapeHtml(token)}">${escapeHtml(token)}</span>`;
            } else {
              passageHtml += escapeHtml(token);
            }
          }
        }

        if (fullHtml) fullHtml += ' ';
        fullHtml += passageHtml;
      }
    });

    correctedHeroBox.innerHTML = fullHtml;

    // Translation sub-block corresponding to active tab
    const fullArabic = getFullArabicTranslation();
    if (fullArabic) {
      const sub = document.createElement('div');
      sub.id = 'sentence-arabic-meaning';
      sub.className = 'sentence-translation-sub';
      sub.textContent = fullArabic;
      correctedHeroBox.appendChild(sub);
    }

    // Attach click events to clickable words
    correctedHeroBox.querySelectorAll('.clickable-word').forEach((el) => {
      el.addEventListener('click', () => {
        const word = el.getAttribute('data-word');
        inspectWord(word);
      });
    });
  }

  // Clickable Word Inspector
  async function inspectWord(word) {
    if (!word) return;
    speakGerman(word);

    try {
      const res = await fetch('/api/word', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word }),
      });
      if (res.ok) {
        const data = await res.json();
        state.currentWordData = data;
        inspWordDe.textContent = data.german_word || word;
        inspWordAr.textContent = data.arabic_meaning ? `— ${data.arabic_meaning}` : '';
        wordInspector.classList.add('show');
      }
    } catch (e) {
      console.warn('Word inspect error:', e);
    }
  }

  // Render Section 4: Replaced Errors List (Cumulative across passage with Category Filtering)
  function renderSection4() {
    if (!replacementsContainer) return;
    replacementsContainer.innerHTML = '';

    const allReplacements = [];
    state.sessionPassages.forEach((p) => {
      if (p.replacements && p.replacements.length > 0) {
        allReplacements.push(...p.replacements);
      }
    });

    if (allReplacements.length === 0) {
      if (state.sessionPassages.length > 0) {
        replacementsContainer.innerHTML = `
          <div style="background:#FFFFFF; border:1px solid var(--sec4-border); border-radius:var(--radius-md); padding:12px; color:#059669; font-weight:700;">
            ✨ ممتاز! لم يتم رصد أي أخطاء في هذه القطعة حتى الآن.
          </div>`;
      }
      return;
    }

    // Apply Filter
    const filter = state.sec4Filter || 'all';
    const filtered = allReplacements.filter((rep) => {
      if (filter === 'all') return true;
      const cat = rep.category || 'grammar';
      if (filter === 'logic_l1') {
        return cat === 'logic_l1' || rep.arabic_trap === true;
      }
      return cat === filter;
    });

    if (filtered.length === 0) {
      replacementsContainer.innerHTML = `
        <div style="background:#FFFFFF; border:1px solid var(--sec4-border); border-radius:var(--radius-md); padding:12px; color:#6B7280; font-weight:600;">
          لا توجد عناصر مطابقة لهذا التصنيف في القطعة الحالية.
        </div>`;
      return;
    }

    filtered.forEach((rep) => {
      const card = document.createElement('div');
      card.className = 'replacement-card';

      const cat = rep.category || 'grammar';
      const catBadge = cat === 'logic_l1'
        ? '<span class="badge-cat-logic">🟠 منطق وفخ عربي</span>'
        : (cat === 'style' ? '<span class="badge-cat-style">🔵 أسلوب وتدفق</span>' : '<span class="badge-cat-grammar">🔴 قواعد ونحو</span>');

      const trapBadge = rep.arabic_trap ? '<span class="badge-trap">⚠️ فخ ترجمة عربية</span>' : '';
      const ruleBadge = rep.rule_tag ? `<span class="badge-rule-tag">${escapeHtml(rep.rule_tag)}</span>` : '';

      const rightArHtml = rep.right_ar
        ? `<span class="rep-right-ar" style="color: #059669; font-weight: 700;">(${escapeHtml(rep.right_ar)})</span>`
        : '';

      const explanation = rep.explanation_ar || rep.why || '';
      const whyHtml = explanation
        ? `<div class="rep-explanation" style="margin-top: 6px; color: #92400E; font-size: 0.92rem; font-weight: 600;">
             <span style="color: #B45309; font-weight: 700;">الشرح:</span> ${escapeHtml(explanation)}
           </div>`
        : '';

      let exampleBoxHtml = '';
      if (rep.example) {
        exampleBoxHtml = `
          <div class="rep-example-box" style="margin-top: 6px;">
            <div class="rep-example de-text" style="font-weight: 600; color: #1E293B; font-size: 0.95rem;">
              <span style="color: #D97706; font-weight: 700;">مثال:</span> ${escapeHtml(rep.example)}
            </div>
            ${rep.example_ar ? `
              <div class="rep-example-ar" style="font-size: 0.88rem; color: #059669;">
                <span style="font-weight: 700;">الترجمة:</span> ${escapeHtml(rep.example_ar)}
              </div>
            ` : ''}
          </div>
        `;
      }

      const wrongVal = rep.original || rep.wrong || '';
      const rightVal = rep.correction || rep.right || '';

      card.innerHTML = `
        <div class="rep-top-row" style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
          <div class="rep-words de-text" style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span class="rep-wrong">${escapeHtml(wrongVal)}</span>
            <span style="color: #94A3B8;">➔</span>
            <span class="rep-right">${escapeHtml(rightVal)}</span>
            ${rightArHtml}
          </div>
          <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
            ${catBadge}
            ${trapBadge}
            ${ruleBadge}
          </div>
        </div>
        ${whyHtml}
        ${exampleBoxHtml}
        <div class="rep-actions" style="margin-top: 10px;">
          <button type="button" class="btn-icon-sm btn-speak-rep" title="استمع لنطق البديل والمثال">🔊</button>
          <button type="button" class="btn-icon-sm btn-copy-rep" title="نسخ البديل والترجمة">📋</button>
          <button type="button" class="btn-icon-sm btn-clip-rep" title="حفظ بالحافظة">📌</button>
          <button type="button" class="btn-chip btn-ask-rep">اسأل المساعد عن هذا الخطأ</button>
        </div>
      `;

      card.querySelector('.btn-speak-rep').onclick = () => speakGerman(rightVal || rep.example);
      card.querySelector('.btn-copy-rep').onclick = () => copyToClipboard(`${wrongVal} ➔ ${rightVal}${rep.right_ar ? ` (${rep.right_ar})` : ''} - ${explanation}`);
      card.querySelector('.btn-clip-rep').onclick = () => saveClipDirect(rightVal, rep.right_ar ? `${rep.right_ar} — ${explanation}` : explanation, rep.category);
      card.querySelector('.btn-ask-rep').onclick = () => {
        assistantQuestionInput.value = `لماذا استبدلنا "${wrongVal}" بـ "${rightVal}" في هذه الجملة؟`;
        sendAssistantQuestion();
        window.location.hash = '#sec-3';
      };

      replacementsContainer.appendChild(card);
    });
  }

  // Render Section 5: Grammar Radar B2/C1/C2 (Cyan Box - Cumulative across passage)
  function renderSection5() {
    if (!radarRulesContainer) return;
    radarRulesContainer.innerHTML = '';

    const allRules = [];
    state.sessionPassages.forEach((p) => {
      if (p.radarRules && p.radarRules.length > 0) {
        allRules.push(...p.radarRules);
      }
    });

    if (allRules.length === 0) {
      if (state.sessionPassages.length > 0) {
        radarRulesContainer.innerHTML = `
          <div style="background:#FFFFFF; border:1px solid var(--sec5-border); border-radius:var(--radius-md); padding:12px; color:#0891B2;">
            لا توجد تراكيب نحوية متقدمة إضافية مرصودة في هذه الجملة.
          </div>`;
      }
      return;
    }

    allRules.forEach((rule) => {
      const item = document.createElement('div');
      item.className = 'rule-card';
      item.innerHTML = `
        <div class="rule-header">
          <span class="rule-name">${escapeHtml(rule.rule_name)}</span>
          <span class="rule-level">${escapeHtml(rule.level || 'B2')}</span>
        </div>
        <div class="rule-desc">${escapeHtml(rule.explanation)}</div>
        ${rule.example_de ? `
          <div class="rule-example-box">
            <div class="de-text" style="font-weight:600; color:#0F766E;">${escapeHtml(rule.example_de)}</div>
            ${rule.example_ar ? `<div style="font-size:0.8rem; color:#115E59;">${escapeHtml(rule.example_ar)}</div>` : ''}
          </div>` : ''}
      `;
      radarRulesContainer.appendChild(item);
    });

    // Refresh cumulative stats
    loadRadarStats();
  }

  async function loadRadarStats() {
    try {
      const res = await fetch('/api/radar');
      if (!res.ok) return;
      const data = await res.json();
      const categories = data.categories || [];

      let trapNoticeHtml = '';
      if (data.arabic_traps_count !== undefined) {
        trapNoticeHtml = `
          <div style="background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 8px; padding: 8px 12px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
            <span style="color: #92400E; font-weight: 700; font-size: 0.88rem;">⚠️ أفخاخ الترجمة من العربي المرصودة:</span>
            <span style="background: #F59E0B; color: #FFF; padding: 2px 8px; border-radius: 12px; font-weight: 800; font-size: 0.82rem;">${data.arabic_traps_count} فخ</span>
          </div>
        `;
      }

      let topRulesHtml = '';
      if (data.top_rule_tags && data.top_rule_tags.length > 0) {
        topRulesHtml = `
          <div style="margin-top: 12px; border-top: 1px dashed #A5F3FC; padding-top: 8px;">
            <div style="font-size: 0.82rem; font-weight: 700; color: #0891B2; margin-bottom: 6px;">🎯 أكثر القواعد المستهدفة:</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
              ${data.top_rule_tags.slice(0, 6).map((t) => `<span style="background: #CFFAFE; color: #0E7490; padding: 3px 8px; border-radius: 12px; font-size: 0.78rem; font-weight: 700;">${escapeHtml(t.rule_tag)} (${t.count})</span>`).join('')}
            </div>
          </div>
        `;
      }

      if (categories.length === 0 && !trapNoticeHtml) {
        radarStatsBars.innerHTML = '<p style="color:#155E75; font-size:0.85rem;">لا توجد إحصائيات تراكمية مسجلة بعد.</p>';
        return;
      }

      const barsHtml = categories
        .slice(0, 5)
        .map(
          (c) => `
          <div class="radar-stat-bar">
            <div class="stat-bar-label">
              <span>${escapeHtml(c.category === 'logic_l1' ? '🟠 منطق وترجمة حرفية' : (c.category === 'style' ? '🔵 أسلوب وتدفق' : '🔴 نحو وقواعد'))}</span>
              <span>${c.count} تكرار (${c.percentage}%)</span>
            </div>
            <div class="stat-bar-track">
              <div class="stat-bar-fill" style="width: ${c.percentage}%; ${c.category === 'logic_l1' ? 'background: #F97316;' : (c.category === 'style' ? 'background: #3B82F6;' : 'background: #EF4444;')}"></div>
            </div>
          </div>
        `
        )
        .join('');

      radarStatsBars.innerHTML = trapNoticeHtml + barsHtml + topRulesHtml;
    } catch (e) {
      console.warn('Failed to load radar stats:', e);
    }
  }

  // ============================================================================
  // Section 3: Saved Conversation Turns (/api/turns)
  // ============================================================================
  async function loadTurns() {
    if (!turnsList) return;
    try {
      const res = await fetch('/api/turns');
      if (!res.ok) return;
      const data = await res.json();
      const items = data.items || [];

      if (items.length === 0) {
        turnsList.innerHTML = `<p style="color: #059669; font-size: 0.85rem; padding: 6px 0;">لا توجد محادثات محفوظة بعد. اضغط "حفظ بالمحادثة +" لإضافتها هنا.</p>`;
        return;
      }

      turnsList.innerHTML = '';
      items.forEach((turn) => {
        const card = document.createElement('div');
        card.className = 'turn-card';
        card.innerHTML = `
          <div class="turn-text-block">
            <div class="turn-de de-text">${escapeHtml(turn.corrected_german)}</div>
            ${turn.arabic_meaning ? `<div class="turn-ar">${escapeHtml(turn.arabic_meaning)}</div>` : ''}
          </div>
          <div class="turn-actions">
            <button type="button" class="btn-icon-sm btn-speak-turn" title="استمع">🔊</button>
            <button type="button" class="btn-icon-sm btn-copy-turn" title="نسخ">📋</button>
            <button type="button" class="btn-icon-sm btn-clip-turn" title="حفظ بالحافظة">📌</button>
            <button type="button" class="btn-icon-sm btn-del-turn" title="حذف" style="color:#DC2626;">🗑️</button>
          </div>
        `;

        card.querySelector('.btn-speak-turn').onclick = () => speakGerman(turn.corrected_german);
        card.querySelector('.btn-copy-turn').onclick = () => copyToClipboard(turn.corrected_german);
        card.querySelector('.btn-clip-turn').onclick = () => saveClipDirect(turn.corrected_german, turn.arabic_meaning, 'Turn');
        card.querySelector('.btn-del-turn').onclick = async () => {
          await fetch(`/api/turns/${turn.id}`, { method: 'DELETE' });
          loadTurns();
          showToast('تم حذف الجملة من المحادثة.', 1800);
        };

        turnsList.appendChild(card);
      });
    } catch (e) {
      console.warn('Failed to load turns:', e);
    }
  }

  async function saveCurrentTurn() {
    const userSentence = mainInput.value.trim();
    let corrected = '';
    let arabicMeaning = '';
    let summaryAr = '';

    if (state.lastCorrection) {
      corrected = state.lastCorrection.corrected_text || userSentence;
      arabicMeaning = state.lastCorrection.arabic_meaning || '';
      summaryAr = state.lastCorrection.summary_ar || '';
    } else {
      corrected = userSentence;
    }

    if (!userSentence && !corrected) {
      showToast('يرجى كتابة أو تصحيح جملة أولاً.', 2000);
      return;
    }

    try {
      const res = await fetch('/api/turns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_sentence: userSentence || corrected,
          corrected_german: corrected,
          arabic_meaning: arabicMeaning,
          is_correct: state.lastCorrection ? state.lastCorrection.is_correct : false,
          summary_ar: summaryAr,
        }),
      });

      if (res.ok) {
        loadTurns();
        showToast('✅ تم حفظ الجملة في سجل المحادثة بنجاح.', 2000);
      }
    } catch (e) {
      showToast('تعذر حفظ الجملة.', 2000);
    }
  }

  async function clearAllTurnsWithUndo() {
    try {
      const res = await fetch('/api/turns');
      const data = await res.json();
      state.deletedTurnsCache = data.items || [];

      if (state.deletedTurnsCache.length === 0) {
        showToast('سجل المحادثات فارغ بالفعل.', 2000);
        return;
      }

      await fetch('/api/turns', { method: 'DELETE' });
      loadTurns();

      showToast('🗑️ تم مسح سجل الجلسة.', 5000, async () => {
        // Undo Action
        if (state.deletedTurnsCache.length > 0) {
          await fetch('/api/turns/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ turns: state.deletedTurnsCache }),
          });
          loadTurns();
          showToast('✅ تم استرجاع المحادثات بنجاح.', 2000);
        }
      });
    } catch (e) {
      showToast('فشل مسح المحادثات.', 2000);
    }
  }

  // ============================================================================
  // Floating Selection Toolbar
  // ============================================================================
  function setupSelectionPopup() {
    document.addEventListener('selectionchange', () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        selectionPopup.classList.remove('show');
        return;
      }

      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        selectionPopup.classList.remove('show');
        return;
      }

      selectionPopup.style.left = `${rect.left + rect.width / 2}px`;
      selectionPopup.style.top = `${rect.top + window.scrollY - 8}px`;
      selectionPopup.classList.add('show');
    });

    selBtnCopy.onclick = () => {
      const selected = window.getSelection().toString().trim();
      copyToClipboard(selected);
      selectionPopup.classList.remove('show');
    };

    selBtnClip.onclick = () => {
      const selected = window.getSelection().toString().trim();
      saveClipDirect(selected);
      selectionPopup.classList.remove('show');
    };

    selBtnSpeak.onclick = () => {
      const selected = window.getSelection().toString().trim();
      speakGerman(selected);
    };

    selBtnAsk.onclick = () => {
      const selected = window.getSelection().toString().trim();
      assistantQuestionInput.value = `ما معنى واستخدام هذا التعبير: "${selected}"؟`;
      sendAssistantQuestion();
      selectionPopup.classList.remove('show');
      window.location.hash = '#sec-3';
    };
  }

  // ============================================================================
  // Section 3: AI Assistant Q&A (/api/ask)
  // ============================================================================
  async function sendAssistantQuestion() {
    const q = assistantQuestionInput.value.trim();
    if (!q) return;

    const currentSentence = state.lastCorrection ? state.lastCorrection.corrected_text : mainInput.value.trim();

    // Render Question Bubble
    const qBubble = document.createElement('div');
    qBubble.className = 'chat-bubble q';
    qBubble.textContent = q;
    assistantChatList.appendChild(qBubble);
    assistantQuestionInput.value = '';
    assistantChatList.scrollTop = assistantChatList.scrollHeight;

    // Loading indicator
    const aBubble = document.createElement('div');
    aBubble.className = 'chat-bubble a';
    aBubble.textContent = 'جاري التفكير... ⏳';
    assistantChatList.appendChild(aBubble);

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, current_sentence: currentSentence }),
      });
      if (!res.ok) throw new Error('فشل الرد من المساعد');

      const data = await res.json();
      let html = `<div>${escapeHtml(data.answer_ar)}</div>`;
      if (data.german_highlight) {
        html += `<div class="de-text" style="font-weight:700; color:#065F46; margin-top:4px;">✨ ${escapeHtml(data.german_highlight)}</div>`;
      }
      if (data.examples && data.examples.length > 0) {
        html += `<ul style="margin:6px 16px 0 0; font-size:0.85rem;" class="de-text">`;
        data.examples.forEach((ex) => (html += `<li>${escapeHtml(ex)}</li>`));
        html += `</ul>`;
      }
      aBubble.innerHTML = html;
      assistantChatList.scrollTop = assistantChatList.scrollHeight;
    } catch (e) {
      aBubble.textContent = `❌ ${e.message}`;
    }
  }

  // ============================================================================
  // Section 6: Persistent Smart Clips (/api/clips)
  // ============================================================================
  async function loadClips() {
    try {
      const res = await fetch('/api/clips');
      if (!res.ok) return;
      const data = await res.json();
      const items = data.items || [];
      state.clipsCount = items.length;
      clipsCountBadge.textContent = state.clipsCount;

      if (items.length === 0) {
        clipsListContainer.innerHTML = `<p style="color: #6D28D9; font-size: 0.9rem;">الحافظة فارغة حالياً. اضغط "حفظ بالحافظة" على أي جملة أو كلمة لحفظها هنا بشكل دائم.</p>`;
        return;
      }

      clipsListContainer.innerHTML = '';
      items.forEach((clip) => {
        const card = document.createElement('div');
        card.className = 'clip-card';
        card.innerHTML = `
          <div class="clip-main-row">
            <div class="clip-texts">
              <span class="clip-de de-text">${escapeHtml(clip.text)}</span>
              ${clip.arabic_meaning ? `<span class="clip-ar">— ${escapeHtml(clip.arabic_meaning)}</span>` : ''}
              ${clip.label ? `<span class="rep-category-badge" style="background:#EDE9FE; color:#5B21B6;">${escapeHtml(clip.label)}</span>` : ''}
            </div>
            <div class="clip-actions">
              <button type="button" class="btn-icon-sm btn-speak-clip" title="استمع">🔊</button>
              <button type="button" class="btn-icon-sm btn-toggle-clip" title="عرض التفاصيل والأمثلة">▼</button>
              <button type="button" class="btn-icon-sm btn-explain-clip" title="توليد أمثلة وشرح جديد">✨</button>
              <button type="button" class="btn-icon-sm btn-copy-clip" title="نسخ">📋</button>
              <button type="button" class="btn-icon-sm btn-del-clip" title="حذف" style="color:#DC2626;">🗑️</button>
            </div>
          </div>
          <div class="clip-details-drawer ${clip.is_open ? 'open' : ''}">
            ${clip.grammar_explanation ? `<div style="font-weight:600; margin-bottom:6px;">📖 ${escapeHtml(clip.grammar_explanation)}</div>` : ''}
            ${clip.synonyms && clip.synonyms.length > 0 ? `<div style="font-size:0.85rem; margin-bottom:4px;"><strong>مرادفات:</strong> <span class="de-text">${escapeHtml(clip.synonyms.join(', '))}</span></div>` : ''}
            <div class="clip-examples-list">
              ${(clip.examples || [])
                .map((ex) => `<div class="rule-example-box"><span class="de-text" style="font-weight:600;">${escapeHtml(ex.de || ex)}</span> ${ex.ar ? `<span>— ${escapeHtml(ex.ar)}</span>` : ''}</div>`)
                .join('')}
            </div>
          </div>
        `;

        const drawer = card.querySelector('.clip-details-drawer');
        card.querySelector('.btn-speak-clip').onclick = () => speakGerman(clip.text);
        card.querySelector('.btn-copy-clip').onclick = () => copyToClipboard(clip.text);
        card.querySelector('.btn-toggle-clip').onclick = () => drawer.classList.toggle('open');
        card.querySelector('.btn-del-clip').onclick = async () => {
          await fetch(`/api/clips/${clip.id}`, { method: 'DELETE' });
          loadClips();
          showToast('تم حذف العنصر من الحافظة.', 1800);
        };
        card.querySelector('.btn-explain-clip').onclick = async () => {
          showToast('جاري توليد شرح وأمثلة سياقية بالذكاء الاصطناعي... ⏳', 3000);
          const expRes = await fetch(`/api/clips/${clip.id}/explain`, { method: 'POST' });
          if (expRes.ok) {
            loadClips();
            showToast('✅ تم تحديث الشرح والأمثلة بنجاح!', 2000);
          }
        };

        clipsListContainer.appendChild(card);
      });
    } catch (e) {
      console.warn('Failed to load clips:', e);
    }
  }

  async function saveClipDirect(text, arabicMeaning = '', label = '') {
    if (!text || !text.trim()) return;
    try {
      if (!arabicMeaning) {
        showToast('جاري حفظ وترجمة التعبير بالذكاء الاصطناعي... ⏳', 3500);
      }
      const res = await fetch('/api/clips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text.trim(),
          arabic_meaning: arabicMeaning,
          label: label,
        }),
      });
      if (res.ok) {
        const savedClip = await res.json();
        loadClips();
        if (savedClip.arabic_meaning) {
          showToast(`📌 تم حفظ وترجمة "${savedClip.text}" بنجاح!`, 2500);
        } else {
          showToast('📌 تم حفظ التعبير في الحافظة الدائمة.', 2000);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(`تعذر حفظ التعبير: ${err.detail || res.statusText}`, 3000);
      }
    } catch (e) {
      showToast('تعذر حفظ التعبير.', 2000);
    }
  }

  // ============================================================================
  // Native Client-Side Word (.docx) Document Generator (Pure JS + JSZip)
  // ============================================================================
  async function generateAndDownloadDocx() {
    showToast('جاري إنشاء ملف Word (.docx)... ⏳', 2500);

    // Fetch latest clips & turns from SQLite
    let clips = [];
    let turns = [];
    try {
      const [resClips, resTurns] = await Promise.all([fetch('/api/clips'), fetch('/api/turns')]);
      clips = (await resClips.json()).items || [];
      turns = (await resTurns.json()).items || [];
    } catch (e) {
      console.warn('Failed to fetch data for export:', e);
    }

    if (clips.length === 0 && turns.length === 0) {
      showToast('⚠️ لا توجد كلمات أو محادثات لتصديرها بعد.', 2500);
      return;
    }

    // Check if JSZip is available
    if (typeof JSZip !== 'undefined') {
      try {
        const zip = new JSZip();

        // 1. [Content_Types].xml
        zip.file(
          '[Content_Types].xml',
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>`
        );

        // 2. _rels/.rels
        zip.file(
          '_rels/.rels',
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`
        );

        // 3. word/_rels/document.xml.rels
        zip.file(
          'word/_rels/document.xml.rels',
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`
        );

        // 4. word/styles.xml
        zip.file(
          'word/styles.xml',
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Traditional Arabic"/>
        <w:sz w:val="24"/>
      </w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
</w:styles>`
        );

        // 5. word/document.xml
        let paragraphsXml = `
          <w:p>
            <w:pPr><w:jc w:val="center"/></w:pPr>
            <w:r><w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="1E3A8A"/></w:rPr><w:t>German Coach 🇩🇪</w:t></w:r>
          </w:p>
          <w:p>
            <w:pPr><w:jc w:val="center"/></w:pPr>
            <w:r><w:rPr><w:sz w:val="24"/><w:color w:val="4B5563"/></w:rPr><w:t>الحافظة الذكية والمحادثات الألمانية المصححة (${state.level})</w:t></w:r>
          </w:p>
          <w:p><w:r><w:t></w:t></w:r></w:p>
        `;

        // Section: Clips
        if (clips.length > 0) {
          paragraphsXml += `
            <w:p>
              <w:r><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="5B21B6"/></w:rPr><w:t>📌 الحافظة الدائمة (${clips.length} تعبير):</w:t></w:r>
            </w:p>
          `;

          clips.forEach((c, idx) => {
            const german = escapeHtml(c.text);
            const arabic = escapeHtml(c.arabic_meaning || '');
            const explanation = escapeHtml(c.grammar_explanation || '');
            const examples = (c.examples || []).map((e) => `• ${escapeHtml(e.de || e)} (${escapeHtml(e.ar || '')})`).join(' | ');

            paragraphsXml += `
              <w:p>
                <w:r><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="065F46"/></w:rPr><w:t>${idx + 1}. ${german}</w:t></w:r>
                <w:r><w:rPr><w:sz w:val="24"/><w:color w:val="1E293B"/></w:rPr><w:t> ➔ ${arabic}</w:t></w:r>
              </w:p>
            `;
            if (explanation) {
              paragraphsXml += `<w:p><w:pPr><w:ind w:left="400"/></w:pPr><w:r><w:rPr><w:i/><w:sz w:val="20"/><w:color w:val="6B7280"/></w:rPr><w:t>الشرح: ${explanation}</w:t></w:r></w:p>`;
            }
            if (examples) {
              paragraphsXml += `<w:p><w:pPr><w:ind w:left="400"/></w:pPr><w:r><w:rPr><w:sz w:val="20"/><w:color w:val="374151"/></w:rPr><w:t>أمثلة: ${examples}</w:t></w:r></w:p>`;
            }
          });
        }

        // Section: Turns
        if (turns.length > 0) {
          paragraphsXml += `
            <w:p><w:r><w:t></w:t></w:r></w:p>
            <w:p>
              <w:r><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="065F46"/></w:rPr><w:t>💬 سجل المحادثات (${turns.length} جملة):</w:t></w:r>
            </w:p>
          `;

          turns.forEach((t, idx) => {
            const de = escapeHtml(t.corrected_german);
            const ar = escapeHtml(t.arabic_meaning || '');
            paragraphsXml += `
              <w:p>
                <w:r><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="0F766E"/></w:rPr><w:t>${idx + 1}. ${de}</w:t></w:r>
                ${ar ? `<w:r><w:rPr><w:sz w:val="24"/><w:color w:val="334155"/></w:rPr><w:t> (${ar})</w:t></w:r>` : ''}
              </w:p>
            `;
          });
        }

        const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${paragraphsXml}
  </w:body>
</w:document>`;

        zip.file('word/document.xml', documentXml);

        const blob = await zip.generateAsync({
          type: 'blob',
          mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        });

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `German_Coach_Vocabulary_${new Date().toISOString().slice(0, 10)}.docx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('✅ تم تحميل ملف Word (.docx) بنجاح!', 3500);
        return;
      } catch (err) {
        console.warn('JSZip failed, falling back to Word HTML .doc:', err);
      }
    }

    // Fallback: Word-compatible HTML format
    downloadHtmlWordFallback(clips, turns);
  }

  function downloadHtmlWordFallback(clips, turns) {
    let content = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>German Coach</title></head>
      <body style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
        <h1 style="color:#1E3A8A; text-align:center;">German Coach 🇩🇪</h1>
        <h3 style="color:#5B21B6;">الحافظة الذكية (${clips.length} تعبير):</h3>
        <ol>
          ${clips.map((c) => `<li><strong style="direction:ltr; display:inline-block;">${c.text}</strong> — ${c.arabic_meaning || ''}</li>`).join('')}
        </ol>
        <h3 style="color:#065F46;">سجل المحادثات (${turns.length} جملة):</h3>
        <ol>
          ${turns.map((t) => `<li><span style="direction:ltr; display:inline-block; font-weight:bold;">${t.corrected_german}</span> ${t.arabic_meaning ? `(${t.arabic_meaning})` : ''}</li>`).join('')}
        </ol>
      </body></html>
    `;
    const blob = new Blob([content], { type: 'application/msword;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `German_Coach_Vocabulary_${new Date().toISOString().slice(0, 10)}.doc`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ تم تحميل الملف بصيغة Word بنجاح.', 3000);
  }

  // ============================================================================
  // Telegram Backup
  // ============================================================================
  async function triggerTelegramBackup() {
    btnTelegramBackup.disabled = true;
    const orig = btnTelegramBackup.innerHTML;
    btnTelegramBackup.innerHTML = '<span>⏳</span><span>جاري النسخ...</span>';

    try {
      const res = await fetch('/api/backup/telegram', { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        showToast('✅ تم إرسال النسخة الاحتياطية لتليجرام بنجاح!', 4000);
      } else {
        const detail = data.detail || 'مفاتيح تليجرام غير مهيأة بعد في السيرفر.';
        showToast(`⚠️ تنبيه: ${detail}`, 5000);
      }
    } catch {
      showToast('❌ تعذر إجراء النسخ الاحتياطي.', 3500);
    } finally {
      btnTelegramBackup.disabled = false;
      btnTelegramBackup.innerHTML = orig;
    }
  }

  // ============================================================================
  // Event Listeners Binding
  // ============================================================================
  function setupEventListeners() {
    // Level selector
    levelSelect.addEventListener('change', (e) => {
      state.level = e.target.value;
      showToast(`تم ضبط المستوى المستهدف على ${state.level}`, 1500);
    });

    // Tone selector (Social Context)
    if (toneSelect) {
      toneSelect.value = state.tone;
      toneSelect.addEventListener('change', (e) => {
        state.tone = e.target.value;
        localStorage.setItem('coach_tone', state.tone);
        showToast(`تم ضبط السياق ونبرة الحديث على ${state.tone === 'Sie' ? 'رسمي (Sie)' : 'ودي (du)'}`, 1500);
      });
    }

    // Section 3 Dual Solution Tabs
    if (tabBtnDirect && tabBtnNative) {
      tabBtnDirect.addEventListener('click', () => {
        state.activeSec3Tab = 'direct';
        tabBtnDirect.classList.add('active');
        tabBtnNative.classList.remove('active');
        renderSection3();
      });
      tabBtnNative.addEventListener('click', () => {
        state.activeSec3Tab = 'native';
        tabBtnNative.classList.add('active');
        tabBtnDirect.classList.remove('active');
        renderSection3();
      });
    }

    // Section 4 Category Filter Chips
    if (sec4FilterChips && sec4FilterChips.length > 0) {
      sec4FilterChips.forEach((chip) => {
        chip.addEventListener('click', () => {
          sec4FilterChips.forEach((c) => c.classList.remove('active'));
          chip.classList.add('active');
          state.sec4Filter = chip.getAttribute('data-filter') || 'all';
          renderSection4();
        });
      });
    }

    // Quick samples
    document.querySelectorAll('.btn-sample').forEach((btn) => {
      btn.addEventListener('click', () => {
        mainInput.value = btn.getAttribute('data-text');
        state.accumulatedSpeech = mainInput.value.trim();
        submitCorrection(false);
      });
    });

    // Mic Buttons
    btnMicDe.addEventListener('click', () => startRecording('de-DE'));
    btnMicAr.addEventListener('click', () => startRecording('ar-EG'));
    if (btnMicStop) {
      btnMicStop.addEventListener('click', () => {
        if (state.isRecording) {
          stopRecording();
          updateLiveStatus('⏹️ تم إيقاف المايك بنجاح.');
          showToast('⏹️ تم إيقاف المايك بنجاح.', 2000);
        } else {
          showToast('ℹ️ المايك متوقف بالفعل.', 1500);
        }
      });
    }
    if (btnDiagMic) btnDiagMic.addEventListener('click', runMicDiagnostic);

    // Input actions
    btnClearInput.addEventListener('click', () => {
      mainInput.value = '';
      state.accumulatedSpeech = '';
      state.lastSubmittedText = '';
      state.lastProcessedLength = 0;
      state.sessionPassages = [];
      clearTimeout(state.typingTimer);
      clearTimeout(state.silenceTimer);
      if (state.currentAbortController) {
        state.currentAbortController.abort();
        state.currentAbortController = null;
      }

      // Reset Section 2, 3, 4, 5 displays cleanly
      renderSection2();
      renderSection3();
      renderSection4();
      renderSection5();

      if (wordInspector) wordInspector.classList.remove('show');
      state.lastCorrection = null;

      // Reset Session Statistics
      state.sessionSentences = 0;
      state.sessionErrors = 0;
      state.sessionCorrect = 0;
      updateSessionStatsUI();

      updateLiveStatus('⚡ تم تفريغ النص والشاشات بنجاح، جاهز للبدء من جديد');
      showToast('🗑️ تم تفريغ النص والشاشات بنجاح', 1800);
    });
    btnCopyInput.addEventListener('click', () => copyToClipboard(mainInput.value, 'تم نسخ النص الكامل 📋'));
    if (btnSaveAsTurn) btnSaveAsTurn.addEventListener('click', saveCurrentTurn);
    btnSubmitCorrect.addEventListener('click', () => submitCorrection(false));

    // Real-time Auto-Correct while typing (live debounce)
    mainInput.addEventListener('input', () => {
      state.accumulatedSpeech = mainInput.value.trim();
      if (!state.autoCorrectEnabled) return;

      clearTimeout(state.typingTimer);
      const text = mainInput.value.trim();
      if (text.length < 3) {
        updateLiveStatus('⚡ اكتب أو تحدث...');
        return;
      }

      // Fast trigger (250ms) on sentence ending punctuation
      const isSentenceEnd = /[.!?؟\n]$/.test(text);
      const delay = isSentenceEnd ? 250 : 650;

      updateLiveStatus('⚡ جاري المتابعة التلقائية...');

      state.typingTimer = setTimeout(() => {
        if (text !== state.lastSubmittedText) {
          submitCorrection(true, false);
        }
      }, delay);
    });

    // Enter key submits immediately
    mainInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        clearTimeout(state.typingTimer);
        submitCorrection(false);
      }
    });

    // Live Automation Toggle Listeners
    if (btnToggleAutoCorrect) {
      btnToggleAutoCorrect.addEventListener('click', () => {
        state.autoCorrectEnabled = !state.autoCorrectEnabled;
        btnToggleAutoCorrect.classList.toggle('active', state.autoCorrectEnabled);
        if (labelAutoCorrect) {
          labelAutoCorrect.textContent = state.autoCorrectEnabled ? '⚡ تصحيح تلقائي فوري: مفعّل' : '⚡ تصحيح تلقائي: معطّل';
        }
        updateLiveStatus(state.autoCorrectEnabled ? '⚡ التصحيح التلقائي الفوري نشط' : '⏸️ التصحيح التلقائي متوقف');
        showToast(state.autoCorrectEnabled ? 'تم تفعيل التصحيح التلقائي الفوري' : 'تم تعطيل التصحيح التلقائي', 1800);
      });
    }

    if (btnToggleContinuousMic) {
      btnToggleContinuousMic.addEventListener('click', () => {
        state.continuousMicEnabled = !state.continuousMicEnabled;
        btnToggleContinuousMic.classList.toggle('active', state.continuousMicEnabled);
        if (labelContinuousMic) {
          labelContinuousMic.textContent = state.continuousMicEnabled ? '🎙️ استماع مستمر (Hands-Free): مفعّل' : '🎙️ استماع مستمر: معطّل';
        }
        showToast(state.continuousMicEnabled ? 'تم تفعيل الاستماع المستمر (Hands-Free)' : 'تم تعطيل الاستماع المستمر', 1800);
      });
    }

    if (btnToggleAutoTts) {
      btnToggleAutoTts.addEventListener('click', () => {
        state.autoTtsEnabled = !state.autoTtsEnabled;
        btnToggleAutoTts.classList.toggle('active', state.autoTtsEnabled);
        if (labelAutoTts) {
          labelAutoTts.textContent = state.autoTtsEnabled ? '🔊 قراءة الكلام تلقائياً: مفعّل' : '🔇 قراءة الكلام تلقائياً: متوقف';
        }
        if (!state.autoTtsEnabled) {
          stopSpeaking();
        }
        showToast(state.autoTtsEnabled ? 'تم تفعيل قراءة الكلام تلقائياً' : 'تم إيقاف قراءة الكلام تلقائياً 🔇', 1800);
      });
    }

    if (btnStopSpeech) {
      btnStopSpeech.addEventListener('click', () => {
        stopSpeaking();
        showToast('تم إيقاف قراءة الكلام فوراً ⏹️', 1500);
      });
    }

    // Section 2 copy original
    if (btnCopyOriginal) {
      btnCopyOriginal.addEventListener('click', () => {
        const fullOriginal = getFullOriginalText();
        if (fullOriginal) {
          copyToClipboard(fullOriginal, 'تم نسخ النص الأصلي للقطعة 📋');
        } else {
          showToast('لا توجد نصوص لنسخها.', 2000);
        }
      });
    }

    // Section 3 actions
    if (btnSpeakCorrected) {
      btnSpeakCorrected.addEventListener('click', () => {
        if ('speechSynthesis' in window && window.speechSynthesis.speaking) {
          stopSpeaking();
          showToast('تم إيقاف قراءة الكلام ⏹️', 1500);
          return;
        }
        const fullGerman = getFullCorrectedGerman();
        if (fullGerman) {
          btnSpeakCorrected.innerHTML = '<span>⏹️</span><span>إيقاف الصوت</span>';
          speakGerman(fullGerman, () => {
            if (btnSpeakCorrected) btnSpeakCorrected.innerHTML = '<span>🔊</span><span>استمع للقطعة</span>';
          });
        } else {
          showToast('لا توجد جملة لنطقها.', 2000);
        }
      });
    }

    if (btnCopyGerman) {
      btnCopyGerman.addEventListener('click', () => {
        const fullGerman = getFullCorrectedGerman();
        if (fullGerman) {
          copyToClipboard(fullGerman, 'تم نسخ القطعة الألمانية المصححة 📋');
        } else {
          showToast('لا توجد جملة لنسخها.', 2000);
        }
      });
    }

    if (btnCopyArabic) {
      btnCopyArabic.addEventListener('click', () => {
        const fullArabic = getFullArabicTranslation();
        if (fullArabic) {
          copyToClipboard(fullArabic, 'تم نسخ ترجمة القطعة العربية 📋');
        } else {
          showToast('لا توجد ترجمة لنسخها.', 2000);
        }
      });
    }

    if (btnClipCorrected) {
      btnClipCorrected.addEventListener('click', () => {
        const fullGerman = getFullCorrectedGerman();
        const fullArabic = getFullArabicTranslation();
        if (fullGerman) {
          saveClipDirect(fullGerman, fullArabic, 'Passage');
        } else {
          showToast('لا توجد جملة لحفظها.', 2000);
        }
      });
    }
    btnTtsToggleRate.addEventListener('click', () => {
      state.speechRate = state.speechRate === 1.0 ? 0.8 : 1.0;
      btnTtsToggleRate.textContent = `${state.speechRate.toFixed(1)}x`;
      showToast(`تم ضبط سرعة النطق على ${state.speechRate.toFixed(1)}x`, 1500);
    });

    // Inspector buttons
    btnInspSpeak.addEventListener('click', () => {
      if (state.currentWordData) speakGerman(state.currentWordData.german_word || state.currentWordData.word);
    });
    btnInspSaveClip.addEventListener('click', () => {
      if (state.currentWordData) {
        saveClipDirect(state.currentWordData.german_word || state.currentWordData.word, state.currentWordData.arabic_meaning, 'Wort');
      }
    });
    btnInspCopy.addEventListener('click', () => {
      if (state.currentWordData) {
        copyToClipboard(`${state.currentWordData.german_word || state.currentWordData.word} (${state.currentWordData.arabic_meaning})`);
      }
    });

    // Turns
    if (btnRefreshTurns) btnRefreshTurns.addEventListener('click', loadTurns);
    if (btnClearTurns) btnClearTurns.addEventListener('click', clearAllTurnsWithUndo);

    // Assistant
    btnAssistantSend.addEventListener('click', sendAssistantQuestion);
    assistantQuestionInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendAssistantQuestion();
      }
    });
    document.querySelectorAll('.btn-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        assistantQuestionInput.value = chip.getAttribute('data-prompt');
        sendAssistantQuestion();
      });
    });

    // Radar
    btnRefreshRadar.addEventListener('click', loadRadarStats);

    // Clips Toolbar
    btnAddClipManual.addEventListener('click', () => {
      const text = prompt('أدخل الكلمة أو التعبير الألماني المراد حفظه (سيتم استخراج الترجمة والشرح بالذكاء الاصطناعي تلقائياً):');
      if (text && text.trim()) {
        saveClipDirect(text.trim(), '', 'Manual');
      }
    });

    btnPasteExplainClip.addEventListener('click', async () => {
      let text = '';
      try {
        text = await navigator.clipboard.readText();
      } catch {
        text = prompt('الصق التعبير أو الجملة الألمانية:');
      }
      if (text && text.trim()) {
        saveClipDirect(text.trim(), '', 'Clipboard');
      }
    });

    btnExportClipsDocx.addEventListener('click', generateAndDownloadDocx);
    btnExportWord.addEventListener('click', generateAndDownloadDocx);

    btnExportClipsJson.addEventListener('click', async () => {
      const res = await fetch('/api/clips');
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data.items || [], null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `german_coach_clips_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('✅ تم تصدير الحافظة بصيغة JSON.', 2000);
    });

    btnImportClipsJson.addEventListener('click', () => importJsonFileInput.click());
    importJsonFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async (ev) => {
        try {
          const parsed = JSON.parse(ev.target.result);
          const clipsArr = Array.isArray(parsed) ? parsed : parsed.items || [];
          const res = await fetch('/api/clips/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ clips: clipsArr }),
          });
          if (res.ok) {
            loadClips();
            showToast('✅ تم استيراد الحافظة بنجاح.', 2500);
          }
        } catch {
          showToast('❌ ملف JSON غير صالح.', 3000);
        }
      };
      reader.readAsText(file);
    });

    btnClearAllClips.addEventListener('click', async () => {
      if (confirm('هل أنت متأكد من رغبتك في تفريغ الحافظة بالكامل؟')) {
        await fetch('/api/clips', { method: 'DELETE' });
        loadClips();
        showToast('تم تفريغ الحافظة.', 2000);
      }
    });

    // Telegram Backup
    btnTelegramBackup.addEventListener('click', triggerTelegramBackup);

    // Help modal
    btnOpenHelp.addEventListener('click', () => helpModal.classList.add('open'));
    btnCloseHelp.addEventListener('click', () => helpModal.classList.remove('open'));
    helpModal.addEventListener('click', (e) => {
      if (e.target === helpModal) helpModal.classList.remove('open');
    });

    // Notice close
    if (micNoticeClose) {
      micNoticeClose.addEventListener('click', () => {
        micNotice.classList.remove('show');
        micNotice.style.display = 'none';
      });
    }
  }

  // ============================================================================
  // Initialization
  // ============================================================================
  document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    setupSelectionPopup();
    checkServerHealth();
    loadTurns();
    loadClips();
    loadRadarStats();
  });
})();
