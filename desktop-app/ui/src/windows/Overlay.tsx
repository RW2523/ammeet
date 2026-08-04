// The Speak overlay — a compact always-on-top panel (docs/ARCHITECTURE §1.6):
// draggable header with the pill summary, collapsible to just the pill,
// points checklist, live nudges, last transcript line, Finish → inline Wrap.

import { useEffect, useMemo, useState } from "react";
import { LogicalSize } from "@tauri-apps/api/dpi";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { api, isTauri } from "../ipc";
import { useEngineSync, useSession } from "../store";
import type { Point } from "../types";

const WIDTH = 340;
const COLLAPSED_HEIGHT = 48;
const EXPANDED_HEIGHT = 520;

function pointIcon(p: Point): { glyph: string; cls: string } {
  if (p.status === "covered") return { glyph: "✓", cls: "pt-covered" };
  if (p.status === "missed") return { glyph: "✕", cls: "pt-missed" };
  if (p.priority === "must") return { glyph: "●", cls: "pt-must" };
  return { glyph: "○", cls: "pt-pending" };
}

export default function Overlay() {
  useEngineSync();
  const s = useSession();
  const [collapsed, setCollapsed] = useState(false);
  const [finishing, setFinishing] = useState(false);

  // Collapsed = just the pill: shrink the actual window so the invisible
  // remainder of the transparent surface can't swallow clicks.
  useEffect(() => {
    if (!isTauri) return;
    void getCurrentWindow()
      .setSize(
        new LogicalSize(WIDTH, collapsed ? COLLAPSED_HEIGHT : EXPANDED_HEIGHT),
      )
      .catch(() => {});
  }, [collapsed]);

  const stages = useMemo(() => {
    const order: string[] = [];
    for (const p of s.points) if (!order.includes(p.stage)) order.push(p.stage);
    return order;
  }, [s.points]);

  const pill =
    s.total > 0
      ? `${s.covered}/${s.total}${s.mustRemaining > 0 ? ` · ${s.mustRemaining} must left` : ""}`
      : s.phase === "running"
        ? "listening…"
        : "no session";

  const live = s.phase === "running" || s.phase === "starting";

  const finish = async () => {
    setFinishing(true);
    try {
      await api.stopSession();
    } catch {
      /* errors surface via engine://event */
    } finally {
      setFinishing(false);
    }
  };

  return (
    <div className={`overlay ${collapsed ? "collapsed" : ""}`}>
      {/* Header: drag region + pill + collapse toggle */}
      <div className="ov-head" data-tauri-drag-region="">
        <span
          className={`ov-dot ${live ? "live" : s.phase === "wrapped" ? "done" : ""}`}
          data-tauri-drag-region=""
        />
        <span className="ov-pill" data-tauri-drag-region="">
          {pill}
        </span>
        <button
          className="ov-toggle"
          title={collapsed ? "Expand" : "Collapse to pill"}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? "▸" : "▾"}
        </button>
      </div>

      {!collapsed && (
        <div className="ov-body">
          {s.phase === "wrapped" && s.wrap ? (
            <div className="ov-wrap">
              <h3>Session wrap</h3>
              <p className="ov-wrap-counts">
                <span className="c-covered">{s.wrap.coveredCount} covered</span>
                {" · "}
                <span className="c-missed">{s.wrap.missedCount} missed</span>
              </p>
              {s.wrap.summary && <p className="ov-wrap-summary">{s.wrap.summary}</p>}
              {s.wrap.missedItems.length > 0 && (
                <div className="ov-missed-list">
                  <p className="ov-label">Missed</p>
                  {s.wrap.missedItems.map((m, i) => (
                    <p key={i} className="ov-missed-item">
                      — {m}
                    </p>
                  ))}
                </div>
              )}
              <button className="btn btn-primary ov-done" onClick={() => s.reset()}>
                Done
              </button>
            </div>
          ) : s.points.length === 0 && !live ? (
            <div className="ov-empty">
              <p>No active session.</p>
              <button className="link" onClick={() => void api.showSettings()}>
                Open Settings to start one
              </button>
            </div>
          ) : (
            <>
              {/* Points checklist */}
              <div className="ov-points">
                {stages.map((stage) => (
                  <div key={stage} className="ov-stage">
                    <p className="ov-label">{stage}</p>
                    {s.points
                      .filter((p) => p.stage === stage)
                      .map((p) => {
                        const icon = pointIcon(p);
                        const flash = s.newlyCovered.includes(p.id);
                        return (
                          <div
                            key={p.id}
                            className={`ov-point ${icon.cls} ${flash ? "flash" : ""}`}
                          >
                            <span className="ov-point-icon">{icon.glyph}</span>
                            <span className="ov-point-text">{p.text}</span>
                          </div>
                        );
                      })}
                  </div>
                ))}
                {s.points.length === 0 && (
                  <p className="ov-hint">Waiting for checklist…</p>
                )}
              </div>

              {/* Nudges — newest on top, max 5 */}
              {s.nudges.length > 0 && (
                <div className="ov-nudges">
                  {s.nudges.map((n) => (
                    <div key={n.key} className={`ov-nudge nudge-${n.kind}`}>
                      <p className="ov-nudge-label">
                        {n.kind === "promise"
                          ? "You promised this"
                          : n.kind === "unanswered"
                            ? "Left unanswered"
                            : n.kind === "conflict"
                              ? "Conflicts with earlier"
                              : "Heads up"}
                      </p>
                      <p className="ov-nudge-text">{n.text}</p>
                      {n.evidence && (
                        <p className="ov-nudge-evidence">“{n.evidence}”</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Last transcript line */}
              {s.lastTranscript && (
                <p className="ov-transcript">
                  <b>{s.lastTranscript.speaker}:</b> {s.lastTranscript.text}
                </p>
              )}

              {live && (
                <button
                  className="btn btn-finish"
                  disabled={finishing}
                  onClick={() => void finish()}
                >
                  {finishing ? "Finishing…" : "Finish"}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
