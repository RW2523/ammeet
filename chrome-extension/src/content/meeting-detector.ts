/**
 * AmMeeting Content Script — Meeting Detector
 *
 * Injected into Zoom, Google Meet, and Microsoft Teams web pages.
 * Detects meeting state from the DOM and URL, scrapes participant info,
 * and sends MEETING_DETECTED / MEETING_ENDED messages to the service worker.
 *
 * Runs as an ISOLATED world content script (cannot access page JS variables).
 * Communicates with service worker via chrome.runtime.sendMessage.
 */

import type { DetectedMeeting, MeetingPlatform, ExtensionMessage } from "../lib/types";
import { startCaptionCapture, stopCaptionCapture } from "./caption-scraper";

// ─── Lifecycle guard ──────────────────────────────────────────────────────────
// After the extension is reloaded/updated, the OLD content script keeps running in
// the page. Its timers/observers still fire, and chrome.runtime.sendMessage then
// throws "Extension context invalidated" SYNCHRONOUSLY (so a .catch() never sees it).
// We detect that, send safely, and tear the orphaned script down so it goes quiet.
let _alive = true;
const _timers: ReturnType<typeof setInterval>[] = [];
let _observer: MutationObserver | null = null;

function contextValid(): boolean {
  try {
    return _alive && !!chrome.runtime?.id;
  } catch {
    return false;
  }
}

function teardown(): void {
  if (!_alive) return;
  _alive = false;
  _timers.forEach(clearInterval);
  _timers.length = 0;
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
  try { _observer?.disconnect(); } catch { /* noop */ }
  try { stopCaptionCapture(); } catch { /* noop */ }
}

function sendToSW(msg: ExtensionMessage): void {
  if (!contextValid()) {
    teardown();
    return;
  }
  try {
    const p = chrome.runtime.sendMessage(msg);
    // May return a promise (SW asleep) or throw synchronously (context invalidated).
    if (p && typeof (p as Promise<unknown>).catch === "function") {
      (p as Promise<unknown>).catch(() => {});
    }
  } catch {
    teardown(); // "Extension context invalidated" — stop the orphaned script.
  }
}

// ─── Notetaker: scrape live captions from THIS tab → service worker ───────────
// Activated by the side panel via the service worker (NOTETAKER_SET_ACTIVE).
chrome.runtime.onMessage.addListener((msg: ExtensionMessage) => {
  if (!contextValid()) return;
  if (msg.type === "NOTETAKER_SET_ACTIVE") {
    if (msg.active) {
      startCaptionCapture((seg) =>
        sendToSW({ type: "NOTETAKER_CAPTION", speaker: seg.speaker, text: seg.text })
      );
    } else {
      stopCaptionCapture();
    }
  }
});

// ─── Platform detection ───────────────────────────────────────────────────────

function detectPlatform(): MeetingPlatform {
  const host = location.hostname;
  if (host.includes("zoom.us")) return "zoom";
  if (host.includes("meet.google.com")) return "meet";
  if (host.includes("teams.microsoft.com")) return "teams";
  return "unknown";
}

function isInMeeting(platform: MeetingPlatform): boolean {
  switch (platform) {
    case "zoom":
      // Zoom web client: wc/<meeting-id>/join or wc/<meeting-id>/start
      return /\/wc\/[0-9]+\/(join|start)/.test(location.pathname) ||
        // Zoom meeting URL before redirect
        document.querySelector(".meeting-client") !== null ||
        document.querySelector('[data-testid="meeting-title"]') !== null;

    case "meet":
      // Google Meet: in a meeting if the footer toolbar is present
      return (
        document.querySelector('[data-call-ended="false"]') !== null ||
        document.querySelector('[jsname="Czc8O"]') !== null || // mic button
        document.querySelector('[data-tooltip*="microphone"]') !== null ||
        /meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}/.test(location.href)
      );

    case "teams":
      // Teams: in a call if the call toolbar is visible
      return (
        document.querySelector('[data-tid="calling-screen"]') !== null ||
        document.querySelector('[data-tid="toggle-mute"]') !== null ||
        location.href.includes("calls")
      );

    default:
      return false;
  }
}

function extractMeetingId(platform: MeetingPlatform): string | null {
  switch (platform) {
    case "zoom": {
      const match = location.pathname.match(/\/wc\/([0-9]+)\//);
      return match?.[1] ?? null;
    }
    case "meet": {
      const match = location.href.match(/meet\.google\.com\/([a-z]{3}-[a-z]{4}-[a-z]{3})/);
      return match?.[1] ?? null;
    }
    case "teams": {
      const match = location.href.match(/meetup-join\/([^/]+)\//);
      return match?.[1] ?? null;
    }
    default:
      return null;
  }
}

function scrapeParticipants(platform: MeetingPlatform): string[] {
  const names: string[] = [];

  try {
    switch (platform) {
      case "zoom": {
        // Zoom participants panel
        document
          .querySelectorAll(
            '.participants-item__display-name, [data-testid="participant-name"]'
          )
          .forEach((el) => {
            const t = el.textContent?.trim();
            if (t) names.push(t);
          });
        break;
      }
      case "meet": {
        // Google Meet participant names
        document
          .querySelectorAll(
            '[data-requested-participant-id] [jsname], .KF4T6b, [jsname="gqyNsd"]'
          )
          .forEach((el) => {
            const t = el.textContent?.trim();
            if (t && t.length < 60) names.push(t);
          });
        break;
      }
      case "teams": {
        document
          .querySelectorAll(
            '[data-tid="participant-item-name"], .ui-text.participant-item__name'
          )
          .forEach((el) => {
            const t = el.textContent?.trim();
            if (t) names.push(t);
          });
        break;
      }
    }
  } catch {
    // DOM scraping is best-effort
  }

  return [...new Set(names)].slice(0, 30);
}

// ─── State tracking ───────────────────────────────────────────────────────────

let _inMeeting = false;
let _platform: MeetingPlatform = detectPlatform();
let _pollInterval: ReturnType<typeof setInterval> | null = null;

function buildDetectedMeeting(): DetectedMeeting {
  return {
    platform: _platform,
    tabId: -1, // service worker fills this from sender.tab.id
    url: location.href,
    title: document.title,
    participants: scrapeParticipants(_platform),
    meetingId: extractMeetingId(_platform),
    detectedAt: Date.now(),
  };
}

function checkMeetingState() {
  if (!contextValid()) {
    teardown();
    return;
  }
  const nowIn = isInMeeting(_platform);

  if (nowIn && !_inMeeting) {
    _inMeeting = true;
    sendToSW({ type: "MEETING_DETECTED", meeting: buildDetectedMeeting() });
    // Refresh participants every 30 s while in meeting
    if (!_pollInterval) {
      _pollInterval = setInterval(() => {
        if (_inMeeting) {
          sendToSW({ type: "MEETING_DETECTED", meeting: buildDetectedMeeting() });
        }
      }, 30_000);
    }
  } else if (!nowIn && _inMeeting) {
    _inMeeting = false;
    sendToSW({ type: "MEETING_ENDED", tabId: -1 });
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

// Check immediately + poll (participant joins/leaves).
checkMeetingState();
_timers.push(setInterval(checkMeetingState, 3000));

// Watch for SPA navigation / UI changes — but Meet mutates the DOM constantly, so
// DEBOUNCE to at most one check per 500ms (avoids hammering + repeated error spam).
let _moDebounce: ReturnType<typeof setTimeout> | null = null;
_observer = new MutationObserver(() => {
  if (_moDebounce || !_alive) return;
  _moDebounce = setTimeout(() => {
    _moDebounce = null;
    checkMeetingState();
  }, 500);
});
if (document.body) _observer.observe(document.body, { childList: true, subtree: true });

// Detect SPA URL changes (Meet/Teams are single-page apps).
let _lastHref = location.href;
_timers.push(
  setInterval(() => {
    if (location.href !== _lastHref) {
      _lastHref = location.href;
      checkMeetingState();
    }
  }, 1000)
);

// Cleanup on unload.
window.addEventListener("beforeunload", () => {
  if (_inMeeting) sendToSW({ type: "MEETING_ENDED", tabId: -1 });
  teardown();
});
