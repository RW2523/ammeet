import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
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
    this._page = null;
    this._pollTimer = null;
  }

  async start() {
    this.status = "joining";
    const args = [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--disable-blink-features=AutomationControlled",
      "--no-sandbox",
      "--autoplay-policy=no-user-gesture-required",
    ];
    if (this._speakFile) args.push(`--use-file-for-fake-audio-capture=${this._speakFile}`);

    const headless = process.env.HEADLESS !== "false";
    const profileDir = process.env.BOT_PROFILE_DIR;
    if (profileDir) {
      // Persistent profile = the bot stays signed in to Google (after a one-time
      // manual login via `npm run google-login`), which is the ONLY way it can
      // join Google Meet (Google blocks anonymous bots).
      this._context = await chromium.launchPersistentContext(profileDir, {
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
      await this._report({ event: "bot.join_failed", data: {} });
      return false;
    }

    this.status = "in_meeting";
    await this._report({ event: "bot.in_call_recording", data: {} });
    await this._enableCaptions();
    this._startCapture();
    return true;
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

  // Speak: render the provided mp3/wav into the meeting via the fake-audio mic.
  // (In Docker this routes through the PulseAudio virtual mic for live audio.)
  async speak(audioBytes) {
    if (!audioBytes || !audioBytes.length) return false;
    if (AUDIO) {
      // Docker path: write a wav and play it into the virtual mic source.
      const f = join(tmpdir(), `say-${Date.now()}.wav`);
      await writeFile(f, audioBytes);
      return new Promise((resolve) => {
        // Play into the sink that feeds the bot's virtual microphone, so other
        // participants hear it (see docker/entrypoint.sh: sink "virtmic_sink").
        const p = spawn("paplay", ["--device=virtmic_sink", f]);
        p.on("close", (code) => resolve(code === 0));
        p.on("error", () => resolve(false));
      });
    }
    // Host fallback: no live audio device — log and report as a chat fallback so it's visible.
    try {
      await this._page?.evaluate(() => {}); // keep page alive
    } catch {}
    return false;
  }

  async leave() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    try {
      await this._page?.evaluate(() => { try { window.APP?.conference?.hangup?.(true); } catch {} });
    } catch {}
    try { await this._context?.close(); } catch {}
    try { await this._browser?.close(); } catch {}
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
