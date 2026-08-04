//! All `#[tauri::command]`s exposed to the webviews.
//!
//! Every command uses `rename_all = "snake_case"` so the TS side passes
//! snake_case argument keys (`workspace_id`, not `workspaceId`) — matching the
//! backend's own naming.

use crate::config;
use crate::core_api::{self, UiSource};
use crate::events::{self, point_payload};
use crate::state::{spawn_drain, AppState, RunningSession};
use crate::window_ctl;
use ammeet_core::{ApiConfig, Auth};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::sync::Notify;

type CmdResult<T> = Result<T, String>;

/// Clone the api config + auth out of state (brief lock, no await inside).
async fn auth_ctx(state: &State<'_, AppState>) -> CmdResult<(ApiConfig, Auth)> {
    let inner = state.inner.lock().await;
    let auth = inner
        .auth
        .as_ref()
        .map(core_api::clone_auth)
        .ok_or_else(|| "Not logged in".to_string())?;
    Ok((core_api::api(&inner.config.base_url), auth))
}

fn emit_status(app: &AppHandle, payload: Value) {
    let _ = app.emit(events::SESSION_STATUS, payload);
}

#[tauri::command(rename_all = "snake_case")]
pub async fn login(
    app: AppHandle,
    state: State<'_, AppState>,
    base_url: String,
    email: String,
    password: String,
) -> CmdResult<Value> {
    let base_url = config::normalize_base_url(&base_url);
    if base_url.is_empty() {
        return Err("Backend URL is required".into());
    }
    let email = email.trim().to_string();
    if email.is_empty() {
        return Err("Email is required".into());
    }

    let api = core_api::api(&base_url);
    let auth = core_api::login(&api, &email, &password).await?;

    let phase = {
        let mut inner = state.inner.lock().await;
        inner.auth = Some(auth);
        inner.fsm.on_login();
        inner.config.base_url = base_url.clone();
        inner.config.email = email.clone();
        if let Err(e) = config::save(&inner.config_dir, &inner.config) {
            eprintln!("[ammeet] failed to persist config: {e}");
        }
        inner.fsm.phase()
    };
    emit_status(&app, json!({ "phase": phase }));
    Ok(json!({ "ok": true, "email": email, "base_url": base_url }))
}

#[tauri::command(rename_all = "snake_case")]
pub async fn get_config(state: State<'_, AppState>) -> CmdResult<Value> {
    let inner = state.inner.lock().await;
    Ok(json!({
        "base_url": inner.config.base_url,
        "email": inner.config.email,
        "whisper_model": inner.config.whisper_model,
        "model_dir": inner.config.model_dir,
        "logged_in": inner.auth.is_some(),
        "phase": inner.fsm.phase(),
    }))
}

#[tauri::command(rename_all = "snake_case")]
pub async fn list_workspaces(state: State<'_, AppState>) -> CmdResult<Value> {
    let (api, auth) = auth_ctx(&state).await?;
    core_api::list_workspaces(&api, &auth).await
}

#[tauri::command(rename_all = "snake_case")]
pub async fn list_meetings(state: State<'_, AppState>, workspace_id: String) -> CmdResult<Value> {
    let (api, auth) = auth_ctx(&state).await?;
    core_api::list_meetings(&api, &auth, &workspace_id).await
}

#[tauri::command(rename_all = "snake_case")]
pub async fn create_meeting(
    state: State<'_, AppState>,
    workspace_id: String,
    title: String,
) -> CmdResult<Value> {
    let title = title.trim().to_string();
    if title.is_empty() {
        return Err("Meeting title is required".into());
    }
    let (api, auth) = auth_ctx(&state).await?;
    core_api::create_meeting(&api, &auth, &workspace_id, &title).await
}

#[tauri::command(rename_all = "snake_case")]
pub async fn generate_points(
    state: State<'_, AppState>,
    workspace_id: String,
    meeting_id: String,
    notes: String,
) -> CmdResult<Value> {
    let (api, auth) = auth_ctx(&state).await?;
    let points = core_api::generate_points(&api, &auth, &workspace_id, &meeting_id, &notes).await?;
    Ok(Value::Array(points.iter().map(point_payload).collect()))
}

/// Resolve where whisper models live: explicit arg → persisted config →
/// `<app-data>/models`.
async fn resolve_model_dir(
    app: &AppHandle,
    state: &State<'_, AppState>,
    dir: Option<String>,
) -> CmdResult<PathBuf> {
    if let Some(d) = dir.filter(|d| !d.trim().is_empty()) {
        return Ok(PathBuf::from(d));
    }
    {
        let inner = state.inner.lock().await;
        if let Some(d) = inner.config.model_dir.as_ref().filter(|d| !d.is_empty()) {
            return Ok(PathBuf::from(d));
        }
    }
    let base = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("cannot resolve app data dir: {e}"))?;
    Ok(base.join("models"))
}

#[tauri::command(rename_all = "snake_case")]
pub async fn pick_model(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    dir: Option<String>,
) -> CmdResult<String> {
    let model_dir = resolve_model_dir(&app, &state, dir).await?;
    let _ = app.emit(
        events::MODEL_PROGRESS,
        json!({ "name": name, "status": "preparing" }),
    );
    match core_api::ensure_model(&model_dir, &name).await {
        Ok(path) => {
            let path_str = path.to_string_lossy().into_owned();
            {
                let mut inner = state.inner.lock().await;
                inner.config.whisper_model = name.clone();
                inner.config.model_dir = Some(model_dir.to_string_lossy().into_owned());
                if let Err(e) = config::save(&inner.config_dir, &inner.config) {
                    eprintln!("[ammeet] failed to persist config: {e}");
                }
            }
            let _ = app.emit(
                events::MODEL_PROGRESS,
                json!({ "name": name, "status": "ready", "path": path_str }),
            );
            Ok(path_str)
        }
        Err(e) => {
            let _ = app.emit(
                events::MODEL_PROGRESS,
                json!({ "name": name, "status": "error", "message": e }),
            );
            Err(e)
        }
    }
}

#[tauri::command(rename_all = "snake_case")]
pub async fn start_session(
    app: AppHandle,
    state: State<'_, AppState>,
    workspace_id: String,
    meeting_id: String,
    source: UiSource,
    model: Option<String>,
    finalize_on_end: Option<bool>,
) -> CmdResult<Value> {
    // Phase-gate + snapshot everything we need, all under one brief lock.
    let (api, auth, model_name, model_dir_cfg) = {
        let mut inner = state.inner.lock().await;
        let auth = inner
            .auth
            .as_ref()
            .map(core_api::clone_auth)
            .ok_or_else(|| "Not logged in".to_string())?;
        inner.fsm.try_start().map_err(|e| e.to_string())?; // Idle -> Running
        (
            core_api::api(&inner.config.base_url),
            auth,
            model
                .filter(|m| !m.trim().is_empty())
                .unwrap_or_else(|| inner.config.whisper_model.clone()),
            inner.config.model_dir.clone(),
        )
    };
    emit_status(
        &app,
        json!({ "phase": "starting", "workspace_id": workspace_id, "meeting_id": meeting_id }),
    );

    let started = start_session_inner(
        &app,
        &state,
        api,
        auth,
        &workspace_id,
        &meeting_id,
        source,
        &model_name,
        model_dir_cfg,
        finalize_on_end.unwrap_or(true),
    )
    .await;

    match started {
        Ok(()) => {
            emit_status(
                &app,
                json!({ "phase": "running", "workspace_id": workspace_id, "meeting_id": meeting_id }),
            );
            Ok(json!({ "ok": true }))
        }
        Err(e) => {
            // Revert the transitional Running phase.
            {
                let mut inner = state.inner.lock().await;
                inner.running = None;
                inner.fsm.on_ended();
            }
            emit_status(&app, json!({ "phase": "idle" }));
            Err(e)
        }
    }
}

#[allow(clippy::too_many_arguments)]
async fn start_session_inner(
    app: &AppHandle,
    state: &State<'_, AppState>,
    api: ApiConfig,
    auth: Auth,
    workspace_id: &str,
    meeting_id: &str,
    source: UiSource,
    model_name: &str,
    model_dir_cfg: Option<String>,
    finalize_on_end: bool,
) -> CmdResult<()> {
    let model_dir = resolve_model_dir(app, state, model_dir_cfg).await?;
    let model_path = core_api::ensure_model(&model_dir, model_name).await?;

    let cfg = core_api::engine_config(
        api,
        auth,
        workspace_id.to_string(),
        meeting_id.to_string(),
        core_api::to_source(source),
        model_path,
        finalize_on_end,
    );
    let (handle, rx) = core_api::start_engine(cfg).await?;

    let ended = Arc::new(Notify::new());
    {
        let mut inner = state.inner.lock().await;
        inner.running = Some(RunningSession {
            handle,
            ended: ended.clone(),
        });
    }
    spawn_drain(app.clone(), rx, ended);
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
pub async fn stop_session(app: AppHandle, state: State<'_, AppState>) -> CmdResult<Value> {
    let running = {
        let mut inner = state.inner.lock().await;
        inner.running.take()
    };
    let mut clean = true;
    if let Some(run) = running {
        // Sync stop signal; the engine then emits Wrap (if finalizing) + Ended,
        // which the drain task forwards to the UI before notifying us.
        run.handle.stop();
        clean = tokio::time::timeout(Duration::from_secs(8), run.ended.notified())
            .await
            .is_ok();
    }
    {
        let mut inner = state.inner.lock().await;
        inner.fsm.on_ended();
    }
    emit_status(&app, json!({ "phase": "idle" }));
    Ok(json!({ "ok": true, "clean": clean }))
}

#[tauri::command(rename_all = "snake_case")]
pub fn toggle_overlay(app: AppHandle) {
    window_ctl::toggle_overlay(&app);
}

#[tauri::command(rename_all = "snake_case")]
pub fn show_settings(app: AppHandle) {
    window_ctl::show_settings(&app);
}

#[tauri::command(rename_all = "snake_case")]
pub fn quit(app: AppHandle) {
    app.exit(0);
}
