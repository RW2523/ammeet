// Mirrors of the Rust-side payloads. See src-tauri/src/events.rs for the
// wire contract: every engine payload carries a `type` tag equal to the
// ammeet-core EngineEvent variant name.

export const ENGINE_EVENT = "engine://event";
export const MODEL_PROGRESS = "model://progress";
export const SESSION_STATUS = "session://status";

export const DEFAULT_BASE_URL = "https://spark-9f46.tail1917c3.ts.net:8443";

export interface Point {
  id: string;
  text: string;
  stage: string;
  priority: string; // "must" is accented; anything else is normal
  status: string; // "pending" | "covered" | "missed"
}

export type EngineEvent =
  | { type: "Transcript"; speaker: string; text: string }
  | {
      type: "State";
      covered: number;
      total: number;
      must_remaining: number;
      newly_covered: string[] | null;
    }
  | { type: "Nudge"; kind: string; text: string; evidence?: string | null }
  | { type: "Points"; points: Point[] }
  | {
      type: "Wrap";
      summary: string;
      // Tolerant: counts or lists, depending on what the engine ships.
      covered: number | string[];
      missed: number | string[];
    }
  | { type: "Error"; message: string; fatal: boolean }
  | { type: "Ended" };

export interface SessionStatusPayload {
  phase: "not_logged_in" | "idle" | "starting" | "running";
  workspace_id?: string;
  meeting_id?: string;
}

export interface ModelProgress {
  name: string;
  status: "preparing" | "ready" | "error";
  path?: string;
  message?: string;
}

export interface AppConfigPayload {
  base_url: string;
  email: string;
  whisper_model: string;
  model_dir: string | null;
  logged_in: boolean;
  phase: string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  [k: string]: unknown;
}

export interface MeetingInfo {
  id: string;
  title: string;
  [k: string]: unknown;
}

export type SourceSpec =
  | { type: "mic"; device: string | null }
  | { type: "wav"; path: string };

export type NudgeKind = "promise" | "unanswered" | "conflict" | "other";

/** Engine may ship enum variant names ("Promise") — normalize to lowercase. */
export function normalizeNudgeKind(kind: string): NudgeKind {
  const k = kind.toLowerCase();
  if (k === "promise" || k === "unanswered" || k === "conflict") return k;
  return "other";
}

/** Wrap.covered / Wrap.missed tolerant count. */
export function asCount(v: number | string[]): number {
  return typeof v === "number" ? v : v.length;
}

/** Wrap.covered / Wrap.missed tolerant item list. */
export function asItems(v: number | string[]): string[] {
  return Array.isArray(v) ? v : [];
}
