/**
 * AmMeeting Chrome Extension — Background Service Worker (Manifest V3)
 *
 * Responsibilities:
 *  - Central message broker between content scripts ↔ side panel ↔ popup
 *  - Manages authentication state (persisted in chrome.storage)
 *  - Makes backend API calls on behalf of other extension contexts
 *  - Handles chrome.notifications for escalation alerts
 *  - Keeps side panel open when a meeting is detected
 *  - Opens side panel automatically on meeting detection
 */

import { ApiClient, ApiError } from "../lib/api";
import {
  getStoredState,
  setStoredState,
  getAuth,
  setAuth,
  clearAuth,
  getBackendUrl,
} from "../lib/store";
import type { ExtensionMessage, DetectedMeeting, StoredState } from "../lib/types";

// ── Keep-alive alarm (service workers sleep after ~30 s) ─────────────────────
chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepalive") {
    // Just waking the SW
    void getStoredState();
  }
});

// ── On install / update ───────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  console.log("[AmMeeting SW] Installed");
});

// ── Tab lifecycle — detect when a meeting tab is closed ───────────────────────
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const state = await getStoredState();
  if (state.detectedMeeting?.tabId === tabId) {
    await setStoredState({ detectedMeeting: null });
    broadcastToAll({ type: "MEETING_ENDED", tabId });
  }
});

// ── Side panel: open on browser action click ─────────────────────────────────
chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id) {
    await chrome.sidePanel.open({ tabId: tab.id });
  }
});

// ── Main message handler ──────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg: ExtensionMessage, sender, sendResponse) => {
  handleMessage(msg, sender)
    .then(sendResponse)
    .catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      sendResponse({ type: "ERROR", message });
    });
  return true; // keep message channel open for async response
});

async function handleMessage(
  msg: ExtensionMessage,
  sender: chrome.runtime.MessageSender
): Promise<ExtensionMessage | null> {
  const backendUrl = await getBackendUrl();
  const auth = await getAuth();
  const api = new ApiClient(backendUrl, auth.accessToken);

  switch (msg.type) {
    // ── Auth ────────────────────────────────────────────────────────────────
    case "LOGIN": {
      const tokens = await api.login(msg.email, msg.password);
      api.setToken(tokens.access_token);
      const me = await api.getMe();
      const newAuth = {
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: me,
      };
      await setAuth(newAuth);
      const authMsg: ExtensionMessage = { type: "AUTH_STATE_CHANGED", auth: newAuth };
      broadcastToAll(authMsg);
      return authMsg;
    }

    case "LOGOUT": {
      await clearAuth();
      const authMsg: ExtensionMessage = {
        type: "AUTH_STATE_CHANGED",
        auth: { accessToken: null, refreshToken: null, user: null },
      };
      broadcastToAll(authMsg);
      return authMsg;
    }

    case "GET_AUTH_STATE": {
      return { type: "AUTH_STATE_CHANGED", auth };
    }

    // ── Workspaces ──────────────────────────────────────────────────────────
    case "GET_WORKSPACES": {
      const workspaces = await api.getWorkspaces();
      return { type: "WORKSPACES_RESULT", workspaces };
    }

    // ── Meetings ────────────────────────────────────────────────────────────
    case "GET_MEETINGS": {
      const meetings = await api.getMeetings(msg.workspaceId);
      return { type: "MEETINGS_RESULT", meetings };
    }

    // ── Questions ───────────────────────────────────────────────────────────
    case "GET_QUESTIONS": {
      const questions = await api.getQuestions(msg.workspaceId, msg.meetingId);
      return { type: "QUESTIONS_RESULT", questions };
    }

    // ── Meeting detected by content script ──────────────────────────────────
    case "MEETING_DETECTED": {
      const dm: DetectedMeeting = msg.meeting;
      await setStoredState({ detectedMeeting: dm });

      // Auto-open side panel in the meeting tab
      if (dm.tabId) {
        chrome.sidePanel.open({ tabId: dm.tabId }).catch(() => {});
      }

      // Notify all other contexts (side panel)
      broadcastToAll(msg, sender.id);

      // Show notification
      chrome.notifications.create("meeting-detected", {
        type: "basic",
        iconUrl: chrome.runtime.getURL("icons/icon48.png"),
        title: "AmMeeting — Meeting Detected",
        message: `${platformLabel(dm.platform)} meeting detected. Click to open AmMeeting.`,
        priority: 2,
      });

      return null;
    }

    case "MEETING_ENDED": {
      await setStoredState({ detectedMeeting: null, botStatus: "idle", sessionStatus: "inactive" });
      broadcastToAll(msg, sender.id);
      return null;
    }

    // ── Session control ─────────────────────────────────────────────────────
    case "START_SESSION": {
      const result = await api.joinMeeting(
        msg.workspaceId,
        msg.meetingId,
        msg.meetingUrl ?? `${backendUrl}/mock-meeting`,
        msg.simulate ?? false
      );
      await setStoredState({
        currentWorkspaceId: msg.workspaceId,
        currentMeetingId: msg.meetingId,
        sessionStatus: "active",
        botStatus: "joining",
      });
      const resp: ExtensionMessage = {
        type: "SESSION_STARTED",
        questionsQueued: result.questions_queued,
      };
      broadcastToAll(resp);

      // Escalation notification setup — will come via WS in side panel
      return resp;
    }

    case "STOP_SESSION": {
      try {
        await api.leaveMeeting(msg.workspaceId, msg.meetingId);
      } catch {
        // Ignore if already left
      }
      await setStoredState({ sessionStatus: "inactive", botStatus: "idle" });
      broadcastToAll({ type: "SESSION_STOPPED" });
      return { type: "SESSION_STOPPED" };
    }

    // ── Open side panel ─────────────────────────────────────────────────────
    case "OPEN_SIDEPANEL": {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) await chrome.sidePanel.open({ tabId: tab.id });
      return null;
    }

    default:
      return null;
  }
}

// ── Escalation alert notification ─────────────────────────────────────────────
export function showEscalationNotification(questionText: string) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon48.png"),
    title: "⚠️ AmMeeting — Human Required",
    message: `Escalation: "${questionText.slice(0, 80)}"`,
    priority: 2,
    requireInteraction: true,
  });
}

// ── Broadcast to all extension contexts ──────────────────────────────────────
function broadcastToAll(msg: ExtensionMessage, excludeContextId?: string) {
  chrome.runtime.sendMessage(msg).catch(() => {
    // No listeners — side panel not open yet, ignore
  });
}

function platformLabel(p: string): string {
  return { zoom: "Zoom", meet: "Google Meet", teams: "Microsoft Teams", unknown: "Online" }[p] ?? p;
}
