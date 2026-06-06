export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  totp_enabled: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  slug: string;
  created_at: string;
}

export interface Person {
  id: string;
  workspace_id: string;
  name: string;
  role: string | null;
  responsibility: string | null;
  current_work: string | null;
  decision_authority: string | null;
  follow_up: string | null;
  email: string | null;
  is_external: boolean;
  created_at: string;
}

export type MeetingMode = "shadow" | "live_navigator" | "proxy" | "data_collection";
export type MeetingStatus = "draft" | "ready" | "in_progress" | "completed" | "cancelled";

export interface Meeting {
  id: string;
  workspace_id: string;
  title: string;
  purpose: string | null;
  mode: MeetingMode;
  status: MeetingStatus;
  capture_level: number;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  proxy_consent_given: boolean;
  proxy_intro_logged: boolean;
  created_at: string;
}

export type QuestionPriority = "must_ask" | "if_time" | "ask_later" | "answered" | "needs_human";
export type QuestionCategory = "status" | "blocker" | "ownership" | "deadline" | "client" | "decision" | "risk" | "general";
export type QuestionStatus = "pending" | "asked" | "answered" | "skipped" | "escalated";

export interface Question {
  id: string;
  meeting_id: string;
  workspace_id: string;
  text: string;
  category: QuestionCategory;
  priority: QuestionPriority;
  status: QuestionStatus;
  sort_order: number;
  proxy_allowed: boolean;
  human_only: boolean;
  do_not_ask: boolean;
  is_private: boolean;
  escalation_rule: string | null;
  source_context: string | null;
  confidence: number | null;
  created_at: string;
}

export interface Answer {
  id: string;
  meeting_id: string;
  question_id: string | null;
  speaker: string | null;
  text: string;
  is_complete: boolean;
  confidence: number | null;
  captured_at: string;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  workspace_id: string;
  title: string;
  owner: string | null;
  deadline: string | null;
  status: string;
  jira_ticket_ref: string | null;
  created_at: string;
}

export interface Report {
  id: string;
  meeting_id: string;
  workspace_id: string;
  summary: string | null;
  full_json: string | null;
  slack_draft: string | null;
  email_draft: string | null;
  jira_draft: string | null;
  slack_sent: boolean;
  email_sent: boolean;
  jira_updated: boolean;
  created_at: string;
}

export interface PrepBrief {
  meeting: Meeting;
  attendees: Array<{ name: string; role?: string; email?: string }>;
  previous_summary: string | null;
  open_action_items: ActionItem[];
  pending_jira_tickets: Array<{
    key: string;
    summary: string;
    status: string;
    assignee: string;
    blockers: string[];
  }>;
  risks: Array<{ id: string; text: string; severity: string }>;
  suggested_questions: Question[];
  suggested_agenda: string[];
}

export interface ProxyEvent {
  type: "disclosure" | "asking" | "answered" | "escalation" | "clarifying" | "info" | "session_complete" | "report_ready" | "error" | "bot_status" | "transcript" | "tts_audio";
  question_id?: string;
  text?: string;
  answer?: string;
  analysis?: Record<string, unknown>;
  reason?: string;
  answer_preview?: string;
  message?: string;
  // Bot-specific fields
  status?: string;
  bot_id?: string;
  // Transcript fields
  speaker?: string;
  is_final?: boolean;
  source?: string;
  // TTS fields
  audio_b64?: string;
  voice?: string;
}

export interface MeetingBot {
  bot_db_id: string;
  external_bot_id: string | null;
  provider: string;
  status: string;
  meeting_url: string | null;
  joined_at: string | null;
  left_at: string | null;
  session_active: boolean;
  live_status?: string;
}

export interface TranscriptSegment {
  speaker: string;
  text: string;
  is_final: boolean;
  source?: string;
  timestamp?: number;
}
