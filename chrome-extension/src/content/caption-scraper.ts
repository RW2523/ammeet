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

// Candidate caption containers per platform (first match wins).
const CONTAINERS: Record<Platform, string[]> = {
  meet: ['div[jsname="dsyhDe"]', ".a4cQT", '[aria-label*="aptions" i]', "[data-use-drag-behavior] [jsname]"],
  zoom: [".live-transcription-subtitle__wrap", '[aria-label="Captions"]', ".closed-caption-container"],
  teams: ['[data-tid="closed-caption-renderer-wrapper"]', '[data-tid="closed-caption-renderer"]', ".ui-chat__item"],
  unknown: ["[aria-live]"],
};

function extractSegments(): CaptionSegment[] {
  const segs: CaptionSegment[] = [];
  const p = platform();
  let root: Element | null = null;
  for (const sel of CONTAINERS[p]) {
    root = document.querySelector(sel);
    if (root) break;
  }
  if (!root) return segs;

  // Each caption "row" usually has a speaker label + a text node. Walk direct-ish
  // children and pull (speaker, text). Fall back to splitting "Name: words".
  const rows = root.querySelectorAll(":scope > div, :scope li, :scope > span, [class]");
  const candidates = rows.length ? Array.from(rows) : [root];
  for (const row of candidates) {
    const raw = (row.textContent || "").replace(/\s+/g, " ").trim();
    if (!raw || raw.length < 2) continue;
    const m = raw.match(/^([^:]{1,40}):\s*(.+)$/);
    if (m) segs.push({ speaker: m[1].trim(), text: m[2].trim() });
    else segs.push({ speaker: "Participant", text: raw });
  }
  // If we matched the whole container as one blob, keep just the last line (most recent)
  if (segs.length > 8) return segs.slice(-4);
  return segs;
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
