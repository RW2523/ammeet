// ─── AmMeeting Chrome Extension — Shared Types ───────────────────────────────

export type MeetingPlatform = "zoom" | "meet" | "teams" | "unknown";
export type BotStatus = "idle" | "joining" | "in_meeting" | "leaving" | "done" | "error";
export type SessionStatus = "inactive" | "starting" | "active" | "ended";

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: {
    id: string;
    email: string;
    full_name: string;
  } | null;
}

export interface DetectedMeeting {
  platform: MeetingPlatform;
  tabId: number;
  url: string;
  title: string;
  participants: string[];
  meetingId: string | null;
  detectedAt: number;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
}

export interface MeetingInfo {
  id: string;
  title: string;
  mode: string;
  status: string;
  proxy_consent_given: boolean;
}

export interface Question {
  id: string;
  text: string;
  status: "pending" | "asked" | "answered" | "skipped" | "escalated";
  proxy_allowed: boolean;
  human_only: boolean;
  priority: string;
  category: string;
}

export type ProxyEventType =
  | "disclosure"
  | "asking"
  | "answered"
  | "escalation"
  | "clarifying"
  | "session_complete"
  | "bot_status"
  | "transcript"
  | "tts_audio"
  | "info"
  | "error";

export interface ProxyEvent {
  type: ProxyEventType;
  text?: string;
  question_id?: string;
  answer?: string;
  speaker?: string;
  is_final?: boolean;
  status?: string;
  reason?: string;
  audio_b64?: string;
}

export interface TranscriptLine {
  speaker: string;
  text: string;
  is_final: boolean;
  ts: number;
}

// ─── Chrome Extension Message Types ──────────────────────────────────────────

export type ExtensionMessage =
  | { type: "MEETING_DETECTED"; meeting: DetectedMeeting }
  | { type: "MEETING_ENDED"; tabId: number }
  | { type: "GET_AUTH_STATE" }
  | { type: "AUTH_STATE_CHANGED"; auth: AuthState }
  | { type: "LOGIN"; email: string; password: string }
  | { type: "LOGOUT" }
  | { type: "GET_WORKSPACES" }
  | { type: "WORKSPACES_RESULT"; workspaces: WorkspaceInfo[] }
  | { type: "GET_MEETINGS"; workspaceId: string }
  | { type: "MEETINGS_RESULT"; meetings: MeetingInfo[] }
  | { type: "GET_QUESTIONS"; workspaceId: string; meetingId: string }
  | { type: "QUESTIONS_RESULT"; questions: Question[] }
  | { type: "START_SESSION"; workspaceId: string; meetingId: string; meetingUrl?: string; simulate?: boolean }
  | { type: "SESSION_STARTED"; questionsQueued: number }
  | { type: "STOP_SESSION"; workspaceId: string; meetingId: string }
  | { type: "SESSION_STOPPED" }
  | { type: "PROXY_EVENT"; event: ProxyEvent }
  | { type: "TRANSCRIPT_LINE"; line: TranscriptLine }
  | { type: "OPEN_SIDEPANEL" }
  | { type: "BOT_STATUS_UPDATE"; status: BotStatus; botId?: string }
  // ── Notetaker (bot-free, captures from the user's own tab) ────────────────
  | { type: "START_NOTETAKER"; workspaceId: string; meetingId: string }
  | { type: "STOP_NOTETAKER"; workspaceId: string; meetingId: string }
  | { type: "NOTETAKER_SET_ACTIVE"; active: boolean }
  | { type: "NOTETAKER_CAPTION"; speaker: string; text: string }
  | { type: "NOTETAKER_STATE"; active: boolean; lines: number }
  | { type: "GET_NOTES"; workspaceId: string; meetingId: string }
  | { type: "NOTES_RESULT"; notes: NotetakerNotes }
  | { type: "ERROR"; message: string };

export interface NotetakerNotes {
  summary: string;
  key_points?: string[];
  action_items?: { title: string; owner?: string | null; deadline?: string | null }[];
  decisions?: { text: string; made_by?: string | null }[];
  risks?: { text: string; severity?: string }[];
  open_questions?: string[];
}

// ─── Speak Mode ───────────────────────────────────────────────────────────────
export type SpeakPriority = "must" | "should" | "nice";
export type SpeakPointStatus = "pending" | "covered" | "missed";

export interface SpeakPoint {
  id: string;
  text: string;
  stage: string;
  priority: SpeakPriority;
  order_index: number;
  status: SpeakPointStatus;
  covered_by_text?: string | null;
}

export interface SpeakResponse {
  id: string;
  speaker: string;
  text: string;
  kind: string; // response | question | decision
  point_id: string | null;
}

export interface SpeakState {
  points: SpeakPoint[];
  responses: SpeakResponse[];
  progress: { total: number; covered: number; missed: number; pending: number; must_remaining: number };
  newly_covered?: string[];
}

export interface SpeakSummary {
  summary: string;
  covered: string[];
  missed: string[];
  action_items: { title: string; owner?: string | null }[];
  follow_ups: string[];
  responses: { speaker: string; text: string; kind: string }[];
  report_id?: string;
}

export interface StoredState {
  auth: AuthState;
  backendUrl: string;
  currentWorkspaceId: string | null;
  currentMeetingId: string | null;
  detectedMeeting: DetectedMeeting | null;
  botStatus: BotStatus;
  sessionStatus: SessionStatus;
}

export const DEFAULT_BACKEND_URL = "http://localhost:8010";
