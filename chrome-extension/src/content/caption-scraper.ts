/**
 * Live caption scraper — the bot-free transcript source.
 *
 * When the user turns on closed captions in Google Meet / Zoom / Teams, the meeting
 * platform renders each speaker's recognized speech into the DOM. We scrape those
 * caption lines from the user's OWN tab (no bot, no sign-in, no host admission) and
 * forward them to AmMeeting — exactly how Fathom / tl;dv work.
 *
 * Caption DOM selectors are obfuscated and change over time, so we try several per
 * platform and fall back to a generic "speaker: text" heuristic.
 */

export interface CaptionSegment {
  speaker: string;
  text: string;
}

type Platform = "meet" | "zoom" | "teams" | "unknown";

function platform(): Platform {
  const h = location.hostname;
  if (h.includes("meet.google.com")) return "meet";
  if (h.includes("zoom.us")) return "zoom";
  if (h.includes("teams.microsoft.com")) return "teams";
  return "unknown";
}

// Candidate caption REGION containers per platform (first match wins). Class names
// are obfuscated and change often, so we try several and fall back to aria/role.
const CONTAINERS: Record<Platform, string[]> = {
  meet: [
    'div[jsname="dsyhDe"]',            // caption region (older)
    ".a4cQT",                          // caption region wrapper
    '[jsname="tgaKEf"]',               // caption list
    '[aria-label*="aptions" i]',       // aria fallback ("Captions"/"captions")
    'div[role="region"][aria-label*="aption" i]',
  ],
  zoom: [
    ".live-transcription-subtitle__wrap",
    ".closed-caption-container",
    '[aria-label="Captions"]',
    ".lt-subtitle__text",
  ],
  teams: [
    '[data-tid="closed-caption-renderer-wrapper"]',
    '[data-tid="closed-caption-v2-window-wrapper"]',
    '[data-tid="closed-caption-renderer"]',
  ],
  unknown: ["[aria-live]"],
};

// Per-platform selector for an individual caption ROW inside the region. Empty →
// fall back to reading the region's own innerText, split into lines.
const ROW_SELECTOR: Record<Platform, string> = {
  meet: '.nMcdL, .TBMuR, div[jsname="tgaKEf"] > div',
  zoom: '.lt-subtitle__text, .live-transcription-subtitle__wrap span',
  teams: '[data-tid="closed-caption-text"], .fui-ChatMessageCompact',
  unknown: "",
};

// Turn a raw caption line into {speaker, text}. Meet renders "Speaker\nText"; some
// platforms use "Speaker: Text"; otherwise it's an unattributed line.
function parseLine(raw0: string): CaptionSegment | null {
  const raw = (raw0 || "").replace(/[\u00a0\s]+/g, " ").trim();
  if (!raw || raw.length < 2) return null;
  const colon = raw.match(/^([^:\n]{1,40}):\s*(.+)$/s);
  if (colon) return { speaker: colon[1].trim(), text: colon[2].replace(/\s+/g, " ").trim() };
  const nl = raw.indexOf("\n");
  if (nl > 0 && nl <= 40) {
    const speaker = raw.slice(0, nl).trim();
    const text = raw.slice(nl + 1).replace(/\s+/g, " ").trim();
    if (text) return { speaker: speaker || "Participant", text };
  }
  return { speaker: "Participant", text: raw.replace(/\s+/g, " ") };
}

function extractSegments(): CaptionSegment[] {
  const p = platform();
  let root: HTMLElement | null = null;
  for (const sel of CONTAINERS[p]) {
    root = document.querySelector<HTMLElement>(sel);
    if (root) break;
  }
  if (!root) return [];

  // Prefer structured per-row extraction (each row = one speaker's utterance).
  const rowSel = ROW_SELECTOR[p];
  let sources: string[] = [];
  if (rowSel) {
    const rows = Array.from(root.querySelectorAll<HTMLElement>(rowSel)).filter(
      (el) => (el.innerText || "").trim().length > 1
    );
    if (rows.length) sources = rows.map((r) => r.innerText);
  }
  // Fall back to the region's own text, split into lines (last resort, class-agnostic).
  if (!sources.length) {
    sources = (root.innerText || "").split(/\n{1,}/).map((s) => s.trim()).filter(Boolean);
  }

  const segs: CaptionSegment[] = [];
  for (const src of sources) {
    const seg = parseLine(src);
    if (seg && seg.text.trim().length >= 2) segs.push(seg);
  }
  // Only the most recent few — the settle-based dedup upstream handles growth.
  return segs.slice(-6);
}

let _timer: ReturnType<typeof setInterval> | null = null;
const _seen = new Set<string>();
// Per-speaker in-flight caption: captions grow word-by-word, so hold the latest text
// and only emit once it stops changing — otherwise every growing prefix ("Hi",
// "Hi there", "Hi there team") would be emitted as a separate, fragmented line.
const _pending = new Map<string, string>();

export function startCaptionCapture(onSegment: (s: CaptionSegment) => void) {
  if (_timer) return;
  _seen.clear();
  _pending.clear();
  _timer = setInterval(() => {
    // Longest text per speaker this cycle (the caption row's current full content).
    const current = new Map<string, string>();
    for (const seg of extractSegments()) {
      const prev = current.get(seg.speaker);
      if (!prev || seg.text.length > prev.length) current.set(seg.speaker, seg.text);
    }
    for (const [speaker, text] of current) {
      if (_pending.get(speaker) === text) {
        // Unchanged since last poll → the utterance has settled; emit once.
        const key = `${speaker}|${text}`.slice(0, 200);
        if (!_seen.has(key) && text.trim().length >= 2) {
          _seen.add(key);
          if (_seen.size > 800) _seen.clear();
          onSegment({ speaker, text });
        }
        _pending.delete(speaker);
      } else {
        _pending.set(speaker, text);
      }
    }
  }, 1500);
}

export function stopCaptionCapture() {
  if (_timer) {
    clearInterval(_timer);
    _timer = null;
  }
  _pending.clear();
}

export function captionsLikelyAvailable(): boolean {
  const p = platform();
  return CONTAINERS[p].some((sel) => document.querySelector(sel) !== null);
}
