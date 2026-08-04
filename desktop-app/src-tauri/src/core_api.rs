//! The ONLY module that calls into `ammeet-core` (besides `events.rs`, which
//! pattern-matches `EngineEvent`). The core crate is being built concurrently
//! against this shared contract:
//!
//! ```text
//! ApiConfig{base_url}, Auth{token},
//! async login(cfg, email, password) -> Auth,
//! list_workspaces, list_meetings, create_meeting,
//! generate_points(...) -> Vec<Point>,
//! Source::{ Mic{device: Option<String>}, Wav{path} },
//! EngineConfig{api, auth, workspace_id, meeting_id, source, whisper_model, finalize_on_end},
//! start_engine(cfg) -> (EngineHandle, UnboundedReceiver<EngineEvent>),
//! EngineHandle::stop(),
//! ensure_model(dir, name) -> PathBuf,
//! Point{id, text, stage, priority, status}
//! ```
//!
//! Where the contract is silent, this module assumes (each assumption is a
//! one-line fix HERE if the core crate chose differently):
//!   1. Every fallible call returns `Result<T, E>` with `E: Display`.
//!   2. API calls take `&ApiConfig` / `&Auth` / `&str` params, in the order
//!      (cfg, auth, workspace_id, meeting_id, …).
//!   3. All of them (and `ensure_model` / `start_engine`) are `async`.
//!   4. `list_workspaces` / `list_meetings` / `create_meeting` return types
//!      implement `serde::Serialize` (we forward them to the UI as JSON).
//!   5. `ensure_model(dir: &Path, name: &str)`.
//!   6. `EngineConfig.whisper_model` is a `PathBuf` (the path returned by
//!      `ensure_model`). If it is a `String`, change `engine_config` below.
//!   7. IDs are `String`s (matches the backend's UUID ids).
//!   8. `EngineHandle::stop()` is a synchronous signal (the caller then waits
//!      for `EngineEvent::Ended` on the event channel — see `state.rs`).

use ammeet_core::{ApiConfig, Auth, EngineConfig, EngineEvent, EngineHandle, Point, Source};
use serde::Deserialize;
use serde_json::Value;
use std::path::{Path, PathBuf};
use tokio::sync::mpsc::UnboundedReceiver;

pub type CoreResult<T> = Result<T, String>;

fn err<E: std::fmt::Display>(e: E) -> String {
    format!("{e}")
}

/// Build an `ApiConfig` from a base URL.
pub fn api(base_url: &str) -> ApiConfig {
    ApiConfig {
        base_url: base_url.to_string(),
    }
}

/// Clone an `Auth` using only the contract-stated field.
pub fn clone_auth(a: &Auth) -> Auth {
    Auth {
        token: a.token.clone(),
    }
}

pub async fn login(cfg: &ApiConfig, email: &str, password: &str) -> CoreResult<Auth> {
    ammeet_core::login(cfg, email, password).await.map_err(err)
}

pub async fn list_workspaces(cfg: &ApiConfig, auth: &Auth) -> CoreResult<Value> {
    let ws = ammeet_core::list_workspaces(cfg, auth).await.map_err(err)?;
    serde_json::to_value(ws).map_err(err)
}

pub async fn list_meetings(cfg: &ApiConfig, auth: &Auth, workspace_id: &str) -> CoreResult<Value> {
    let ms = ammeet_core::list_meetings(cfg, auth, workspace_id)
        .await
        .map_err(err)?;
    serde_json::to_value(ms).map_err(err)
}

pub async fn create_meeting(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    title: &str,
) -> CoreResult<Value> {
    let m = ammeet_core::create_meeting(cfg, auth, workspace_id, title)
        .await
        .map_err(err)?;
    serde_json::to_value(m).map_err(err)
}

pub async fn generate_points(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    meeting_id: &str,
    notes: &str,
) -> CoreResult<Vec<Point>> {
    ammeet_core::generate_points(cfg, auth, workspace_id, meeting_id, notes)
        .await
        .map_err(err)
}

pub async fn ensure_model(dir: &Path, name: &str) -> CoreResult<PathBuf> {
    ammeet_core::ensure_model(dir, name).await.map_err(err)
}

pub async fn start_engine(
    cfg: EngineConfig,
) -> CoreResult<(EngineHandle, UnboundedReceiver<EngineEvent>)> {
    ammeet_core::start_engine(cfg).map_err(err)
}

/// Audio source as sent by the UI:
/// `{ "type": "mic", "device": string|null }` or `{ "type": "wav", "path": string }`.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum UiSource {
    Mic {
        #[serde(default)]
        device: Option<String>,
    },
    Wav {
        path: String,
    },
}

pub fn to_source(s: UiSource) -> Source {
    match s {
        UiSource::Mic { device } => Source::Mic { device },
        // `.into()` compiles whether `Source::Wav.path` is `String` or `PathBuf`.
        UiSource::Wav { path } => Source::Wav { path: path.into() },
    }
}

#[allow(clippy::too_many_arguments)]
pub fn engine_config(
    api: ApiConfig,
    auth: Auth,
    workspace_id: String,
    meeting_id: String,
    source: Source,
    whisper_model: PathBuf,
    finalize_on_end: bool,
) -> EngineConfig {
    EngineConfig {
        api,
        auth,
        workspace_id,
        meeting_id,
        source,
        whisper_model,
        finalize_on_end,
    }
}
