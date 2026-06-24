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

export function startCaptionCapture(onSegment: (s: CaptionSegment) => void) {
  if (_timer) return;
  _seen.clear();
  _timer = setInterval(() => {
    for (const seg of extractSegments()) {
      const key = `${seg.speaker}|${seg.text}`.slice(0, 160);
      if (_seen.has(key)) continue;
      // Only emit once a line looks "settled" (avoid partials by requiring the same
      // tail twice). Simple: mark seen and emit; dedup handles repeats.
      _seen.add(key);
      if (_seen.size > 500) _seen.clear();
      if (seg.text.trim().length >= 2) onSegment(seg);
    }
  }, 1500);
}

export function stopCaptionCapture() {
  if (_timer) {
    clearInterval(_timer);
    _timer = null;
  }
}

export function captionsLikelyAvailable(): boolean {
  const p = platform();
  return CONTAINERS[p].some((sel) => document.querySelector(sel) !== null);
}
