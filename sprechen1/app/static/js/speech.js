/**
 * speech.js - محرك التعرف الصوتي المباشر والنطق الصوتي
 * Web Speech Recognition & Speech Synthesis Wrapper
 */

class SpeechEngine {
  constructor() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.isSupported = !!SpeechRec;
    this.recognition = this.isSupported ? new SpeechRec() : null;
    this.isListening = false;
    this.currentLang = 'de-DE';

    // Callbacks
    this.onInterimCallback = null;
    this.onFinalCallback = null;
    this.onStatusChangeCallback = null;
    this.onErrorCallback = null;

    if (this.isSupported) {
      this._setupRecognition();
    }
  }

  _setupRecognition() {
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;
    this.recognition.lang = this.currentLang;

    this.recognition.onstart = () => {
      this.isListening = true;
      if (this.onStatusChangeCallback) this.onStatusChangeCallback(true);
    };

    this.recognition.onend = () => {
      // إذا كان المفترض أن يظل شغالاً، نعيد تشغيله تلقائياً إلا إذا تم إيقافه يدوياً
      if (this.isListening) {
        try {
          this.recognition.start();
        } catch (e) {
          this.isListening = false;
          if (this.onStatusChangeCallback) this.onStatusChangeCallback(false);
        }
      } else {
        if (this.onStatusChangeCallback) this.onStatusChangeCallback(false);
      }
    };

    this.recognition.onerror = (event) => {
      let message = 'حدث خطأ في استقبال الصوت.';
      let isFatal = false;

      switch (event.error) {
        case 'not-allowed':
        case 'service-not-allowed':
          message = 'تم رفض الإذن باستخدام الميكروفون. يرجى تفعيله من إعدادات المتصفح.';
          isFatal = true;
          this.isListening = false;
          break;
        case 'no-speech':
          message = 'لم يتم سماع صوت. المايك بانتظار كلامك...';
          break;
        case 'network':
          message = 'مشكلة في اتصال خدمة التعرف على الصوت. تحقق من الإنترنت.';
          break;
        case 'audio-capture':
          message = 'لم يتم العثور على ميكروفون صالح في الجهاز.';
          isFatal = true;
          this.isListening = false;
          break;
        default:
          message = `تنبيه المايك: ${event.error}`;
      }

      if (this.onErrorCallback) this.onErrorCallback(message, isFatal);
    };

    this.recognition.onresult = (event) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript + ' ';
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript.trim() && this.onFinalCallback) {
        this.onFinalCallback(finalTranscript.trim());
      }

      if (this.onInterimCallback) {
        this.onInterimCallback(interimTranscript);
      }
    };
  }

  setLanguage(langCode) {
    this.currentLang = langCode;
    if (this.recognition) {
      const wasListening = this.isListening;
      if (wasListening) this.stop();
      this.recognition.lang = langCode;
      if (wasListening) this.start();
    }
  }

  start() {
    if (!this.isSupported) {
      if (this.onErrorCallback) {
        this.onErrorCallback('متصفحك لا يدعم Web Speech API. يرجى استخدام متصفح Chrome أو Edge أو الكتابة يدوياً.', true);
      }
      return false;
    }
    this.isListening = true;
    try {
      this.recognition.start();
      return true;
    } catch (e) {
      console.warn('SpeechRecognition start warning:', e);
      return false;
    }
  }

  stop() {
    this.isListening = false;
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {}
    }
    if (this.onStatusChangeCallback) this.onStatusChangeCallback(false);
  }

  toggle() {
    if (this.isListening) {
      this.stop();
    } else {
      this.start();
    }
    return this.isListening;
  }

  // النطق الصوتي الألماني
  speakGerman(text) {
    if (!('speechSynthesis' in window)) {
      alert('ميزة نطق الصوت غير مدعومة في متصفحك.');
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'de-DE';
    utterance.rate = 0.95; // سرعة واضحة للتعلم
    window.speechSynthesis.speak(utterance);
  }
}

window.speechEngine = new SpeechEngine();
