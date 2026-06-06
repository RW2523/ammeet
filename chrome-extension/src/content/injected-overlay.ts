/**
 * AmMeeting Content Script — Injected Overlay
 *
 * Injects a small floating status badge into meeting pages showing:
 *  - Whether AmMeeting is connected
 *  - Bot status (idle / joining / in_meeting / escalation)
 *  - Click to open side panel
 *
 * Designed to be minimally intrusive — uses shadow DOM to avoid style conflicts.
 */

import type { ExtensionMessage } from "../lib/types";

// ─── Create shadow-DOM badge ──────────────────────────────────────────────────

const host = document.createElement("div");
host.id = "ammeet-overlay-host";
host.style.cssText = `
  position: fixed;
  bottom: 80px;
  right: 16px;
  z-index: 2147483647;
  pointer-events: auto;
`;

const shadow = host.attachShadow({ mode: "open" });

const style = document.createElement("style");
style.textContent = `
  :host { all: initial; }
  .badge {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 9999px;
    padding: 6px 12px 6px 8px;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    transition: all 0.2s ease;
    user-select: none;
    min-width: 120px;
  }
  .badge:hover {
    background: #334155;
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(0,0,0,0.5);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #64748b;
    flex-shrink: 0;
    transition: background 0.3s;
  }
  .dot.idle     { background: #64748b; }
  .dot.joining  { background: #f59e0b; animation: pulse 1s infinite; }
  .dot.active   { background: #22c55e; animation: pulse 1.5s infinite; }
  .dot.error    { background: #ef4444; }
  .dot.escalation { background: #f97316; animation: pulse 0.5s infinite; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  .label { flex: 1; white-space: nowrap; }
  .close-btn {
    margin-left: 4px;
    opacity: 0.5;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    padding: 0 2px;
  }
  .close-btn:hover { opacity: 1; }
`;
shadow.appendChild(style);

const badge = document.createElement("div");
badge.className = "badge";
badge.innerHTML = `
  <span class="dot idle"></span>
  <span class="label">AmMeeting</span>
  <span class="close-btn" title="Hide">×</span>
`;
shadow.appendChild(badge);

// ─── Insert badge once DOM is ready ──────────────────────────────────────────

function insertBadge() {
  if (document.body && !document.getElementById("ammeet-overlay-host")) {
    document.body.appendChild(host);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", insertBadge);
} else {
  insertBadge();
}

// ─── Update badge state ───────────────────────────────────────────────────────

type BadgeState = "idle" | "joining" | "active" | "error" | "escalation";

function updateBadge(state: BadgeState, label: string) {
  const dot = shadow.querySelector<HTMLElement>(".dot");
  const lbl = shadow.querySelector<HTMLElement>(".label");
  if (dot) {
    dot.className = `dot ${state}`;
  }
  if (lbl) lbl.textContent = label;
}

// ─── Interaction: click to open side panel ────────────────────────────────────

badge.addEventListener("click", (e) => {
  if ((e.target as HTMLElement).classList.contains("close-btn")) {
    host.style.display = "none";
    return;
  }
  chrome.runtime.sendMessage({ type: "OPEN_SIDEPANEL" } as ExtensionMessage).catch(() => {});
});

// ─── Listen for status updates from service worker / side panel ───────────────

chrome.runtime.onMessage.addListener((msg: ExtensionMessage) => {
  switch (msg.type) {
    case "BOT_STATUS_UPDATE":
      switch (msg.status) {
        case "joining":
          updateBadge("joining", "Bot joining…");
          break;
        case "in_meeting":
          updateBadge("active", "🤖 Bot live");
          break;
        case "done":
        case "idle":
          updateBadge("idle", "AmMeeting");
          break;
        case "error":
          updateBadge("error", "Bot error");
          break;
      }
      break;

    case "PROXY_EVENT":
      if (msg.event.type === "escalation") {
        updateBadge("escalation", "⚠️ Escalation!");
        setTimeout(() => updateBadge("active", "🤖 Bot live"), 5000);
      } else if (msg.event.type === "asking") {
        updateBadge("active", "❓ Asking…");
      } else if (msg.event.type === "answered") {
        updateBadge("active", "✅ Answered");
      } else if (msg.event.type === "session_complete") {
        updateBadge("idle", "✅ Session done");
      }
      break;

    case "SESSION_STARTED":
      updateBadge("active", "🤖 Session active");
      break;

    case "SESSION_STOPPED":
      updateBadge("idle", "AmMeeting");
      break;

    case "MEETING_DETECTED":
      updateBadge("idle", "Meeting detected");
      host.style.display = ""; // make visible
      break;
  }
});
