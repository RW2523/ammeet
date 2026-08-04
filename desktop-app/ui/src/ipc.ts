// Thin wrappers over @tauri-apps/api so components stay declarative and the
// whole UI degrades gracefully when opened in a plain browser (`npm run dev`
// without the Tauri shell).

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type {
  AppConfigPayload,
  MeetingInfo,
  Point,
  SourceSpec,
  WorkspaceInfo,
} from "./types";

export const isTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

async function call<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri) {
    throw new Error(
      "Not running inside the Tauri shell — start via `cargo tauri dev`.",
    );
  }
  return invoke<T>(cmd, args);
}

/** Subscribe to a Tauri event; resolves to an unlisten fn (no-op in browser). */
export async function on<T>(
  event: string,
  handler: (payload: T) => void,
): Promise<UnlistenFn> {
  if (!isTauri) return () => {};
  return listen<T>(event, (e) => handler(e.payload));
}

// Commands use `rename_all = "snake_case"` on the Rust side, so argument keys
// here are snake_case — matching the backend's naming everywhere.
export const api = {
  login: (base_url: string, email: string, password: string) =>
    call<{ ok: boolean; email: string; base_url: string }>("login", {
      base_url,
      email,
      password,
    }),
  getConfig: () => call<AppConfigPayload>("get_config"),
  listWorkspaces: () => call<WorkspaceInfo[]>("list_workspaces"),
  listMeetings: (workspace_id: string) =>
    call<MeetingInfo[]>("list_meetings", { workspace_id }),
  createMeeting: (workspace_id: string, title: string) =>
    call<MeetingInfo>("create_meeting", { workspace_id, title }),
  generatePoints: (workspace_id: string, meeting_id: string, notes: string) =>
    call<Point[]>("generate_points", { workspace_id, meeting_id, notes }),
  pickModel: (name: string, dir?: string | null) =>
    call<string>("pick_model", { name, dir: dir ?? null }),
  startSession: (args: {
    workspace_id: string;
    meeting_id: string;
    source: SourceSpec;
    model?: string;
  }) =>
    call<{ ok: boolean }>("start_session", {
      workspace_id: args.workspace_id,
      meeting_id: args.meeting_id,
      source: args.source,
      model: args.model ?? null,
      finalize_on_end: true,
    }),
  stopSession: () => call<{ ok: boolean; clean: boolean }>("stop_session"),
  toggleOverlay: () => call<void>("toggle_overlay"),
  showSettings: () => call<void>("show_settings"),
  quit: () => call<void>("quit"),
};
