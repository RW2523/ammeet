//! ammeet-core — the Rust core of the AmMeeting desktop app (Phase 2).
//!
//! Capture (mic / wav) → local whisper.cpp STT → the existing backend Speak
//! engine, surfaced as a typed event stream. One brain, many bodies: this
//! crate adds capture and presentation only, never intelligence.
//!
//! The sibling Tauri shell (`src-tauri`) depends on this crate by path and
//! forwards [`EngineEvent`]s to the webview.

mod api;
mod audio;
mod engine;
mod error;
mod model;
mod stt;

pub use api::{
    create_meeting, create_workspace, generate_points, get_speak_state, list_meetings,
    list_workspaces, login, register, speak_finalize, speak_ingest, ApiConfig, Auth, Meeting,
    Nudge, Point, Progress, Segment, SpeakResponse, SpeakState, UserOut, Workspace, WrapReport,
};
pub use audio::{is_speech, load_wav_16k_mono, SAMPLE_RATE, VAD_MEAN_ABS_THRESHOLD};
pub use engine::{
    start_engine, EngineConfig, EngineEvent, EngineHandle, Source, CHUNK_SECONDS, INGEST_EVERY,
};
pub use error::CoreError;
pub use model::ensure_model;
