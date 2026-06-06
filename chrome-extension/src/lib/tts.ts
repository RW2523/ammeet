/**
 * Browser-native TTS using the Web Speech Synthesis API.
 *
 * Falls back to playing base64 MP3 audio (from OpenAI TTS via backend)
 * if speechSynthesis is unavailable or muted.
 *
 * Coverage: all modern browsers support speechSynthesis.
 */

export interface TTSOptions {
  voice?: string;       // voice name substring match, e.g. "Google US English"
  rate?: number;        // 0.5 – 2.0 (default 1.0)
  pitch?: number;       // 0 – 2 (default 1.0)
  volume?: number;      // 0 – 1 (default 1.0)
  lang?: string;        // e.g. "en-US"
}

export class BrowserTTS {
  private _muted = false;
  private _speaking = false;
  private _queue: Array<{ text: string; resolve: () => void }> = [];
  private _audioContext: AudioContext | null = null;

  onSpeakStart: (text: string) => void = () => {};
  onSpeakEnd: (text: string) => void = () => {};

  readonly isSupported = typeof speechSynthesis !== "undefined";

  constructor(private options: TTSOptions = {}) {}

  get muted() {
    return this._muted;
  }
  get speaking() {
    return this._speaking;
  }

  mute() {
    this._muted = true;
    if (this.isSupported) speechSynthesis.cancel();
  }

  unmute() {
    this._muted = false;
  }

  /** Speak text using the Web Speech Synthesis API. */
  speak(text: string): Promise<void> {
    if (!text.trim()) return Promise.resolve();

    return new Promise((resolve) => {
      if (this._muted || !this.isSupported) {
        resolve();
        return;
      }

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = this.options.lang ?? "en-US";
      utterance.rate = this.options.rate ?? 1.0;
      utterance.pitch = this.options.pitch ?? 1.0;
      utterance.volume = this.options.volume ?? 1.0;

      // Pick best matching voice
      const voices = speechSynthesis.getVoices();
      if (voices.length) {
        const target = this.options.voice ?? "Google US English";
        const match =
          voices.find((v) => v.name.includes(target) && v.lang.startsWith("en")) ??
          voices.find((v) => v.lang.startsWith("en") && v.name.toLowerCase().includes("female")) ??
          voices.find((v) => v.lang.startsWith("en")) ??
          voices[0];
        if (match) utterance.voice = match;
      }

      utterance.onstart = () => {
        this._speaking = true;
        this.onSpeakStart(text);
      };
      utterance.onend = () => {
        this._speaking = false;
        this.onSpeakEnd(text);
        resolve();
      };
      utterance.onerror = () => {
        this._speaking = false;
        resolve();
      };

      // Chrome bug: speechSynthesis sometimes pauses after ~15s
      // Workaround: resume() it periodically
      const resumeInterval = setInterval(() => {
        if (speechSynthesis.paused) speechSynthesis.resume();
      }, 5000);
      utterance.onend = () => {
        clearInterval(resumeInterval);
        this._speaking = false;
        this.onSpeakEnd(text);
        resolve();
      };

      speechSynthesis.speak(utterance);
    });
  }

  /** Play base64-encoded MP3 audio (from OpenAI TTS backend response). */
  async playAudioB64(audioB64: string): Promise<void> {
    if (this._muted) return;

    const binary = atob(audioB64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    return this._playBuffer(bytes.buffer);
  }

  /** Play an ArrayBuffer as audio. */
  async playBuffer(buffer: ArrayBuffer): Promise<void> {
    if (this._muted) return;
    return this._playBuffer(buffer);
  }

  private async _playBuffer(buffer: ArrayBuffer): Promise<void> {
    if (!this._audioContext) {
      this._audioContext = new AudioContext();
    }
    const ctx = this._audioContext;
    if (ctx.state === "suspended") await ctx.resume();

    return new Promise((resolve) => {
      ctx.decodeAudioData(
        buffer.slice(0),
        (decoded) => {
          const source = ctx.createBufferSource();
          source.buffer = decoded;
          source.connect(ctx.destination);
          this._speaking = true;
          source.onended = () => {
            this._speaking = false;
            resolve();
          };
          source.start();
        },
        (err) => {
          console.error("TTS audio decode error:", err);
          resolve();
        }
      );
    });
  }

  cancel() {
    if (this.isSupported) speechSynthesis.cancel();
    this._audioContext?.suspend();
    this._speaking = false;
    this._queue = [];
  }

  getVoiceNames(): string[] {
    if (!this.isSupported) return [];
    return speechSynthesis.getVoices().map((v) => `${v.name} (${v.lang})`);
  }
}
