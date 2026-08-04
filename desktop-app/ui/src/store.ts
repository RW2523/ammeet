// Session snapshot shared by both windows, fed exclusively by Tauri events.
// Each webview keeps its own copy; subscribing on mount + the Rust side
// broadcasting to all windows keeps them in sync (reconnect-safe: the overlay
// window exists from app start, so it never misses mid-session events).

import { useEffect } from "react";
import { create } from "zustand";
import { on } from "./ipc";
import {
  asCount,
  asItems,
  ENGINE_EVENT,
  normalizeNudgeKind,
  SESSION_STATUS,
  type EngineEvent,
  type Point,
  type SessionStatusPayload,
} from "./types";

export type Phase = "idle" | "starting" | "running" | "wrapped";

export interface NudgeEntry {
  key: string;
  kind: ReturnType<typeof normalizeNudgeKind>;
  text: string;
  evidence: string | null;
  ts: number;
}

export interface WrapInfo {
  summary: string;
  coveredCount: number;
  missedCount: number;
  coveredItems: string[];
  missedItems: string[];
}

interface SessionStore {
  phase: Phase;
  points: Point[];
  covered: number;
  total: number;
  mustRemaining: number;
  newlyCovered: string[];
  nudges: NudgeEntry[];
  lastTranscript: { speaker: string; text: string } | null;
  wrap: WrapInfo | null;
  lastError: string | null;
  applyEngine: (ev: EngineEvent) => void;
  applyStatus: (status: SessionStatusPayload) => void;
  reset: () => void;
}

const initial = {
  phase: "idle" as Phase,
  points: [] as Point[],
  covered: 0,
  total: 0,
  mustRemaining: 0,
  newlyCovered: [] as string[],
  nudges: [] as NudgeEntry[],
  lastTranscript: null as { speaker: string; text: string } | null,
  wrap: null as WrapInfo | null,
  lastError: null as string | null,
};

const MAX_NUDGES = 5;

export const useSession = create<SessionStore>((set, get) => ({
  ...initial,

  applyEngine: (ev) => {
    switch (ev.type) {
      case "Transcript":
        set({ lastTranscript: { speaker: ev.speaker, text: ev.text } });
        break;
      case "State": {
        const newly = ev.newly_covered ?? [];
        // Defensive: if the engine doesn't re-send Points on coverage change,
        // flip statuses locally for ids/texts named in newly_covered.
        const points =
          newly.length > 0
            ? get().points.map((p) =>
                newly.includes(p.id) || newly.includes(p.text)
                  ? { ...p, status: "covered" }
                  : p,
              )
            : get().points;
        set({
          covered: ev.covered,
          total: ev.total,
          mustRemaining: ev.must_remaining,
          newlyCovered: newly,
          points,
        });
        break;
      }
      case "Nudge": {
        const kind = normalizeNudgeKind(ev.kind);
        const key = `${kind}:${ev.text}`;
        const existing = get().nudges;
        if (existing.some((n) => n.key === key)) break;
        const entry: NudgeEntry = {
          key,
          kind,
          text: ev.text,
          evidence: ev.evidence ?? null,
          ts: Date.now(),
        };
        set({ nudges: [entry, ...existing].slice(0, MAX_NUDGES) });
        break;
      }
      case "Points":
        set({ points: ev.points });
        break;
      case "Wrap":
        set({
          wrap: {
            summary: ev.summary,
            coveredCount: asCount(ev.covered),
            missedCount: asCount(ev.missed),
            coveredItems: asItems(ev.covered),
            missedItems: asItems(ev.missed),
          },
          phase: "wrapped",
        });
        break;
      case "Error":
        set({ lastError: ev.message });
        break;
      case "Ended":
        set({ phase: get().wrap ? "wrapped" : "idle" });
        break;
    }
  },

  applyStatus: (status) => {
    switch (status.phase) {
      case "starting":
        // New session: clear the previous one's residue.
        set({ ...initial, phase: "starting" });
        break;
      case "running":
        set({ phase: "running" });
        break;
      case "idle":
      case "not_logged_in":
        // Keep the wrap on screen until the user dismisses it.
        if (get().phase !== "wrapped") set({ phase: "idle" });
        break;
    }
  },

  reset: () => set({ ...initial }),
}));

/** Subscribe this window to engine + session events for its lifetime. */
export function useEngineSync(): void {
  useEffect(() => {
    let unsubs: Array<() => void> = [];
    let alive = true;
    void (async () => {
      const u1 = await on<EngineEvent>(ENGINE_EVENT, (ev) =>
        useSession.getState().applyEngine(ev),
      );
      const u2 = await on<SessionStatusPayload>(SESSION_STATUS, (s) =>
        useSession.getState().applyStatus(s),
      );
      if (!alive) {
        u1();
        u2();
        return;
      }
      unsubs = [u1, u2];
    })();
    return () => {
      alive = false;
      unsubs.forEach((u) => u());
    };
  }, []);
}
