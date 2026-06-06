import React, { useEffect, useState } from "react";
import type { AuthState, DetectedMeeting, ExtensionMessage, SessionStatus, BotStatus } from "../lib/types";
import { getStoredState } from "../lib/store";

function sendSW(msg: ExtensionMessage): Promise<ExtensionMessage | null> {
  return chrome.runtime.sendMessage(msg).catch(() => null);
}

function clsx(...a: (string | boolean | null | undefined)[]): string {
  return a.filter(Boolean).join(" ");
}

const BOT_COLOR: Record<string, string> = {
  idle: "text-gray-400",
  joining: "text-yellow-400",
  in_meeting: "text-green-400",
  done: "text-gray-400",
  error: "text-red-400",
};

export default function Popup() {
  const [auth, setAuth] = useState<AuthState>({ accessToken: null, refreshToken: null, user: null });
  const [detected, setDetected] = useState<DetectedMeeting | null>(null);
  const [botStatus, setBotStatus] = useState<BotStatus>("idle");
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("inactive");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStoredState().then((s) => {
      setAuth(s.auth);
      setDetected(s.detectedMeeting);
      setBotStatus(s.botStatus as BotStatus);
      setSessionStatus(s.sessionStatus as SessionStatus);
      setLoading(false);
    });
  }, []);

  const openSidePanel = async () => {
    await sendSW({ type: "OPEN_SIDEPANEL" });
    window.close();
  };

  const logout = async () => {
    await sendSW({ type: "LOGOUT" });
    setAuth({ accessToken: null, refreshToken: null, user: null });
  };

  if (loading) {
    return (
      <div className="w-80 p-6 text-center text-gray-500 font-sans text-sm bg-gray-950">
        Loading…
      </div>
    );
  }

  return (
    <div className="w-80 bg-gray-950 text-gray-100 font-sans text-xs">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 bg-gray-900">
        <span className="text-lg">🤖</span>
        <span className="font-bold text-sm text-white">AmMeeting</span>
        <span className="ml-auto text-gray-500">v1.0</span>
      </div>

      <div className="p-4 space-y-3">
        {!auth.accessToken ? (
          /* Not logged in */
          <div className="text-center space-y-3">
            <p className="text-gray-400">Sign in to AmMeeting to activate your AI meeting proxy.</p>
            <button
              onClick={openSidePanel}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-lg py-2 text-sm font-semibold transition"
            >
              Open AmMeeting Panel
            </button>
          </div>
        ) : (
          <>
            {/* User info */}
            <div className="flex items-center gap-2 bg-gray-900 rounded-lg p-2">
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                {(auth.user?.full_name?.[0] ?? auth.user?.email?.[0] ?? "U").toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{auth.user?.full_name}</p>
                <p className="text-gray-500 truncate">{auth.user?.email}</p>
              </div>
            </div>

            {/* Meeting detection status */}
            <div className="bg-gray-900 rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    "w-2 h-2 rounded-full flex-shrink-0",
                    detected ? "bg-green-400 animate-pulse" : "bg-gray-600"
                  )}
                />
                <span className="font-semibold text-gray-200">
                  {detected ? `${detected.platform} meeting detected` : "No meeting detected"}
                </span>
              </div>

              {detected && (
                <div className="text-gray-400 space-y-0.5">
                  <p className="truncate text-gray-300">
                    Meeting ID: {detected.meetingId ?? "unknown"}
                  </p>
                  {detected.participants.length > 0 && (
                    <p>{detected.participants.length} participants visible</p>
                  )}
                </div>
              )}
            </div>

            {/* Session status */}
            <div className="bg-gray-900 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-gray-400 font-semibold">Proxy Session</span>
                <span
                  className={clsx(
                    "px-2 py-0.5 rounded-full text-xs font-semibold uppercase",
                    sessionStatus === "active"
                      ? "bg-green-900 text-green-300"
                      : sessionStatus === "starting"
                      ? "bg-yellow-900 text-yellow-300"
                      : sessionStatus === "ended"
                      ? "bg-gray-800 text-gray-500"
                      : "bg-gray-800 text-gray-500"
                  )}
                >
                  {sessionStatus}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className={clsx("font-medium", BOT_COLOR[botStatus] ?? "text-gray-400")}>
                  Bot: {botStatus.replace(/_/g, " ")}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="space-y-2">
              <button
                onClick={openSidePanel}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-lg py-2 text-sm font-semibold transition"
              >
                {sessionStatus === "active" ? "📊 Open Live Room" : "🚀 Open AmMeeting Panel"}
              </button>

              {detected && sessionStatus === "inactive" && (
                <button
                  onClick={openSidePanel}
                  className="w-full bg-green-700 hover:bg-green-600 text-white rounded-lg py-1.5 text-xs font-semibold transition"
                >
                  🤖 Start Proxy for Detected Meeting
                </button>
              )}

              <button
                onClick={logout}
                className="w-full border border-gray-700 hover:border-gray-500 text-gray-400 hover:text-white rounded-lg py-1.5 text-xs font-semibold transition"
              >
                Sign Out
              </button>
            </div>
          </>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 pb-3 text-center text-gray-700 text-xs">
        AmMeeting v1.0 · AI Meeting Proxy
      </div>
    </div>
  );
}
