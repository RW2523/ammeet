import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { writeFile, unlink, cp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { detectPlatform, JOINERS } from "./platforms.js";

// When running in the Docker image, audio is routed through a PulseAudio virtual
// mic/sink so the bot can capture meeting audio and speak into it. On a plain host
// (no PulseAudio) the bot still JOINS and captures captions/chat.
const AUDIO = process.env.AUDIO_CAPTURE === "pulse";

export class BrowserBot {
  constructor(id, { meetingUrl, displayName = "AmMeeting Assistant", webhookUrl = null }) {
    this.id = id;
    this.meetingUrl = meetingUrl;
    this.displayName = displayName;
    this.webhookUrl = webhookUrl;
    this.platform = detectPlatform(meetingUrl);
    this.status = "created";
    this.transcript = [];
    this._seenCaptions = new Set();
    this._seenChat = new Set();
    this._browser = null;
    this._context = null;
    this._page = null;
    this._pollTimer = null;
    this._workProfile = null;      // per-bot clone of BOT_PROFILE_DIR (avoids lock contention)
    this._speakChain = Promise.resolve();  // serialize speak() so mute state can't race
  }

  async start() {
    this.status = "joining";
    const args = [
      "--use-fake-ui-for-media-stream",   // auto-grant mic/cam permission
      "--disable-blink-features=AutomationControlled",
      "--no-sandbox",
      "--autoplay-policy=no-user-gesture-required",
    ];
    // In PulseAudio mode the bot's microphone must be the REAL default source (the
    // virtual mic we play TTS into) — the synthetic fake device would override it and
    // the meeting would only ever hear a test tone. Only fake the device when we have
    // no audio routing (listen-only) so getUserMedia still succeeds headless.
    if (!AUDIO) args.push("--use-fake-device-for-media-stream");

    const headless = process.env.HEADLESS !== "false";
    const profileDir = process.env.BOT_PROFILE_DIR;
    try {
      if (profileDir) {
        // Persistent profile = the bot stays signed in to Google (after a one-time
        // `npm run google-login`). Clone it per-bot so concurrent bots don't fight
        // over Chromium's single-instance profile lock.
        this._workProfile = join(tmpdir(), `botprofile-${this.id}`);
        await cp(profileDir, this._workProfile, { recursive: true }).catch(() => {});
        this._context = await chromium.launchPersistentContext(this._workProfile, {
          headless,
          args,
          viewport: { width: 1280, height: 720 },
          permissions: ["camera", "microphone"],
        });
        this._page = this._context.pages()[0] || (await this._context.newPage());
      } else {
        this._browser = await chromium.launch({ headless, args });
        this._context = await this._browser.newContext({ permissions: ["camera", "microphone"] });
        this._page = await this._context.newPage();
      }

      const joiner = JOINERS[this.platform] || JOINERS.jitsi;
      const ok = await joiner(this._page, this.meetingUrl, { displayName: this.displayName });
      if (!ok) {
        this.status = "error";
        await this._report({ event: "bot.join_failed", data: {} }).catch(() => {});
        await this._cleanup();
        return false;
      }
    } catch (e) {
      // Any launch/join failure must still tear down the browser + temp profile.
      this.status = "error";
      this.lastError = String(e).slice(0, 300);
      await this._report({ event: "bot.join_failed", data: { error: this.lastError } }).catch(() => {});
      await this._cleanup();
      return false;
    }

    this.status = "in_meeting";
    await this._report({ event: "bot.in_call_recording", data: {} });
    await this._enableCaptions();
    this._startCapture();
    return true;
  }

  // Tear down browser/context/timer/temp-profile. Idempotent; safe on any path.
  async _cleanup() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
    try { await this._context?.close(); } catch {}
    try { await this._browser?.close(); } catch {}
    this._context = null;
    this._browser = null;
    this._page = null;
    if (this._workProfile) {
      try { await rm(this._workProfile, { recursive: true, force: true }); } catch {}
      this._workProfile = null;
    }
  }

  // Toggle Jitsi closed captions (transcription) on, best-effort.
  async _enableCaptions() {
    if (this.platform !== "jitsi") return;
    try {
      await this._page.evaluate(() => {
        try { window.APP?.API?.executeCommand?.("setSubtitles", true, false); } catch {}
        try { window.APP?.store?.dispatch?.({ type: "SET_REQUESTING_SUBTITLES", enabled: true }); } catch {}
      });
    } catch {
      /* non-fatal */
    }
  }

  _startCapture() {
    this._pollTimer = setInterval(() => this._poll().catch(() => {}), 2000);
  }

  async _poll() {
    if (!this._page) return;
    // 1) Live captions / subtitles (each speaker's recognized speech)
    const captions = await this._page
      .evaluate(() => {
        const out = [];
        document.querySelectorAll('[class*="subtitles" i] [class*="line" i], .csi, [data-testid*="subtitle"]').forEach((el) => {
          const t = (el.textContent || "").trim();
          if (t) out.push(t);
        });
        return out;
      })
      .catch(() => []);
    for (const line of captions) {
      const key = line.slice(0, 120);
      if (this._seenCaptions.has(key)) continue;
      this._seenCaptions.add(key);
      const m = line.match(/^([^:]{1,40}):\s*(.+)$/);
      const speaker = m ? m[1].trim() : "Participant";
      const text = m ? m[2].trim() : line;
      await this._emit(speaker, text, "caption");
    }

    // 2) Chat messages
    const chats = await this._page
      .evaluate(() => {
        const out = [];
        document.querySelectorAll('[class*="chatmessage" i], .usermessage, [data-testid="chat-message"]').forEach((el) => {
          const t = (el.textContent || "").trim();
          if (t) out.push(t);
        });
        return out;
      })
      .catch(() => []);
    for (const c of chats) {
      const key = c.slice(0, 120);
      if (this._seenChat.has(key)) continue;
      this._seenChat.add(key);
      await this._emit("Chat", c, "chat");
    }

    // 3) Detect everyone-left / call ended
    const ended = await this._page
      .evaluate(() => {
        try { return window.APP?.conference?.membersCount === 1 ? "alone" : "ok"; } catch { return "ok"; }
      })
      .catch(() => "ok");
    this._lastPresence = ended;
  }

  async _emit(speaker, text, source) {
    const seg = { speaker, text, source, timestamp_ms: Date.now() };
    this.transcript.push(seg);
    await this._report({ event: "transcript.final", data: { text, speaker } });
  }

  // Speak: play the provided audio (mp3 or wav from TTS) into the meeting via the
  // PulseAudio virtual mic. Requires AUDIO_CAPTURE=pulse (the Docker image).
  async speak(audioBytes) {
    if (!audioBytes || !audioBytes.length) return false;
    if (!AUDIO) {
      // Host has no virtual audio device, so nothing can be transmitted — be honest.
      console.warn("[bot] speak() requires AUDIO_CAPTURE=pulse (Docker); no-op on host.");
      return false;
    }
    // Serialize so overlapping output-audio calls can't race the mute toggle.
    this._speakChain = this._speakChain.then(() => this._speakOnce(audioBytes)).catch(() => false);
    return this._speakChain;
  }

  async _speakOnce(audioBytes) {
    // TTS is usually MP3; paplay only accepts WAV. Decode with ffmpeg to a 48kHz mono
    // WAV first, then play into the sink feeding the bot's virtual mic.
    const stamp = `${Date.now()}-${Math.floor(process.hrtime()[1])}`;
    const src = join(tmpdir(), `say-${stamp}.in`);
    const wav = join(tmpdir(), `say-${stamp}.wav`);
    try {
      await writeFile(src, audioBytes);
      const decoded = await new Promise((resolve) => {
        const ff = spawn("ffmpeg", ["-y", "-i", src, "-ar", "48000", "-ac", "1", "-f", "wav", wav]);
        ff.on("close", (code) => resolve(code === 0));
        ff.on("error", () => resolve(false));
      });
      if (!decoded) {
        console.error("[bot] ffmpeg failed to decode TTS audio");
        return false;
      }
      // Unmute the mic so the audio actually transmits, play, then re-mute.
      await this._setMuted(false);
      const played = await new Promise((resolve) => {
        const p = spawn("paplay", ["--device=virtmic_sink", wav]);
        p.on("close", (code) => resolve(code === 0));
        p.on("error", () => resolve(false));
      });
      await this._setMuted(true);
      return played;
    } finally {
      await unlink(src).catch(() => {});
      await unlink(wav).catch(() => {});
    }
  }

  // Toggle the bot's microphone mute state (best-effort, per platform).
  async _setMuted(muted) {
    if (!this._page) return;
    try {
      if (this.platform === "jitsi") {
        await this._page.evaluate((m) => {
          try { window.APP?.API?.executeCommand?.("setAudioMuted", m); } catch {}
          try { window.APP?.conference?.[m ? "muteAudio" : "unmuteAudio"]?.(); } catch {}
        }, muted);
        return;
      }
      // Meet/Teams/Zoom: click the mic toggle by aria-label.
      const on = ['[aria-label*="Turn on microphone" i]', '[aria-label*="Unmute" i]'];
      const off = ['[aria-label*="Turn off microphone" i]', '[aria-label*="Mute" i]'];
      for (const sel of muted ? off : on) {
        const btn = await this._page.$(sel);
        if (btn) { await btn.click().catch(() => {}); break; }
      }
    } catch {
      /* best-effort */
    }
  }

  async leave() {
    try {
      await this._page?.evaluate(() => { try { window.APP?.conference?.hangup?.(true); } catch {} });
    } catch {}
    await this._cleanup();
    this.status = "done";
    await this._report({ event: "bot.call_ended", data: {} });
  }

  async _report(payload) {
    if (!this.webhookUrl) return;
    try {
      await fetch(this.webhookUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      /* webhook unreachable — non-fatal */
    }
  }

  info() {
    return {
      id: this.id,
      platform: this.platform,
      status: this.status,
      segments: this.transcript.length,
      ...(this.lastError ? { error: this.lastError } : {}),
    };
  }
}
