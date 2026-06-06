/**
 * Browser-native STT using the Web Speech API (SpeechRecognition).
 *
 * Coverage:
 *  - Chrome / Edge: full support (webkitSpeechRecognition + SpeechRecognition)
 *  - Firefox / Safari: no support → falls back to null (caller must handle)
 *
 * Usage:
 *   const stt = new BrowserSTT(lang);
 *   stt.onPartial = (text) => ...;
 *   stt.onFinal   = (text) => ...;
 *   stt.onError   = (err)  => ...;
 *   stt.start();
 *   stt.stop();
 */

import "./speech.d";

export type STTEvent = "partial" | "final" | "start" | "stop" | "error";

export class BrowserSTT {
  private recognition: SpeechRecognition | null = null;
  private _running = false;
  private _restartTimer: ReturnType<typeof setTimeout> | null = null;

  onPartial: (text: string) => void = () => {};
  onFinal: (text: string) => void = () => {};
  onStart: () => void = () => {};
  onStop: () => void = () => {};
  onError: (error: string) => void = () => {};

  readonly isSupported: boolean;

  constructor(private lang = "en-US") {
    const Ctor =
      window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;

    this.isSupported = Ctor !== null;

    if (!Ctor) return;

    this.recognition = new Ctor();
    this.recognition.lang = this.lang;
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;

    this.recognition.onstart = () => {
      this._running = true;
      this.onStart();
    };

    this.recognition.onend = () => {
      this._running = false;
      this.onStop();
      // Auto-restart if we didn't explicitly stop
      if (this._shouldRestart) {
        this._restartTimer = setTimeout(() => {
          if (this._shouldRestart) this.start();
        }, 300);
      }
    };

    this.recognition.onresult = (event: SpeechRecognitionEvent) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0].transcript.trim();
        if (!transcript) continue;
        if (result.isFinal) {
          this.onFinal(transcript);
        } else {
          this.onPartial(transcript);
        }
      }
    };

    this.recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const msg = event.error;
      // "no-speech" is normal — don't treat as critical
      if (msg !== "no-speech") {
        this.onError(msg);
      }
    };
  }

  private _shouldRestart = false;

  start() {
    if (!this.recognition) {
      this.onError("SpeechRecognition is not supported in this browser.");
      return;
    }
    this._shouldRestart = true;
    if (!this._running) {
      try {
        this.recognition.start();
      } catch {
        // Already started — ignore
      }
    }
  }

  stop() {
    this._shouldRestart = false;
    if (this._restartTimer) {
      clearTimeout(this._restartTimer);
      this._restartTimer = null;
    }
    if (this.recognition && this._running) {
      try {
        this.recognition.stop();
      } catch {
        // Ignore
      }
    }
  }

  get running() {
    return this._running;
  }

  setLanguage(lang: string) {
    this.lang = lang;
    if (this.recognition) this.recognition.lang = lang;
  }
}

// ─── Tab audio capture via chrome.tabCapture ──────────────────────────────────
// Captures the meeting tab's output audio (what participants say).
// This runs in the SIDE PANEL context where chrome.tabCapture is available.

export async function captureTabAudio(tabId: number): Promise<MediaStream | null> {
  return new Promise((resolve) => {
    if (!chrome?.tabCapture) {
      resolve(null);
      return;
    }
    chrome.tabCapture.capture(
      { audio: true, video: false },
      (stream) => {
        if (chrome.runtime.lastError) {
          console.error("tabCapture error:", chrome.runtime.lastError);
          resolve(null);
        } else {
          resolve(stream ?? null);
        }
      }
    );
  });
}

/**
 * Record a MediaStream to WebM audio chunks.
 * Returns a Blob when recording stops.
 */
export function recordStream(
  stream: MediaStream,
  onChunk?: (chunk: Blob) => void
): { stop: () => Promise<Blob> } {
  const recorder = new MediaRecorder(stream, {
    mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm",
  });

  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) {
      chunks.push(e.data);
      onChunk?.(e.data);
    }
  };

  recorder.start(1000); // emit chunk every 1s

  return {
    stop: () =>
      new Promise((resolve) => {
        recorder.onstop = () => resolve(new Blob(chunks, { type: "audio/webm" }));
        recorder.stop();
        stream.getTracks().forEach((t) => t.stop());
      }),
  };
}
