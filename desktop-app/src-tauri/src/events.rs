//! Mapping from `ammeet_core::EngineEvent` to the JSON payloads emitted to the
//! webviews. Pure functions — no tauri types — so the mapping logic is easy to
//! review and (once the core crate builds) test in isolation.
//!
//! Contract with the UI (mirrored in `ui/src/types.ts`):
//! every payload carries a `type` field equal to the `EngineEvent` variant
//! name (`Transcript` | `State` | `Nudge` | `Points` | `Wrap` | `Error` |
//! `Ended`), with the variant's fields flattened alongside it.

use ammeet_core::{EngineEvent, Point};
use serde_json::{json, Value};

/// Every engine event, re-emitted to all windows.
pub const ENGINE_EVENT: &str = "engine://event";
/// Model preparation progress from `pick_model` / `start_session`.
pub const MODEL_PROGRESS: &str = "model://progress";
/// Session lifecycle changes: `{ "phase": "idle" | "starting" | "running" | … }`.
pub const SESSION_STATUS: &str = "session://status";

/// Serialize a `Point` field-by-field. Done manually (rather than relying on
/// `Point: Serialize`) so the wire shape is pinned here regardless of any
/// serde attributes inside the core crate.
pub fn point_payload(p: &Point) -> Value {
    json!({
        "id": p.id,
        "text": p.text,
        "stage": p.stage,
        "priority": p.priority,
        "status": p.status,
    })
}

/// Tag an `EngineEvent` with its variant name and flatten its fields.
///
/// Patterns use `..` so an extra field added to a variant in the core crate
/// does not break this crate; a renamed/removed variant or field still fails
/// the build loudly (which is what we want).
pub fn engine_event_payload(ev: &EngineEvent) -> Value {
    match ev {
        EngineEvent::Transcript { speaker, text, .. } => json!({
            "type": "Transcript",
            "speaker": speaker,
            "text": text,
        }),
        EngineEvent::State {
            covered,
            total,
            must_remaining,
            newly_covered,
            ..
        } => json!({
            "type": "State",
            "covered": covered,
            "total": total,
            "must_remaining": must_remaining,
            "newly_covered": newly_covered,
        }),
        EngineEvent::Nudge {
            kind,
            text,
            evidence,
            ..
        } => json!({
            "type": "Nudge",
            "kind": kind,
            "text": text,
            "evidence": evidence,
        }),
        EngineEvent::Points { points, .. } => json!({
            "type": "Points",
            "points": points.iter().map(point_payload).collect::<Vec<_>>(),
        }),
        EngineEvent::Wrap {
            summary,
            covered,
            missed,
            ..
        } => json!({
            "type": "Wrap",
            "summary": summary,
            "covered": covered,
            "missed": missed,
        }),
        EngineEvent::Error { message, fatal, .. } => json!({
            "type": "Error",
            "message": message,
            "fatal": fatal,
        }),
        EngineEvent::Ended => json!({ "type": "Ended" }),
    }
}

/// `true` for events that terminate the session (drain task exits on these).
pub fn is_terminal(ev: &EngineEvent) -> bool {
    matches!(
        ev,
        EngineEvent::Ended | EngineEvent::Error { fatal: true, .. }
    )
}
