//! Typed client for the AmMeeting backend ("the brain").
//!
//! All shapes mirror the backend JSON exactly (see `backend/app/routers/*.py`
//! and `/openapi.json`). This module owns every HTTP call the engine makes so
//! the retry/auth policy lives in one place.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;

use crate::error::CoreError;

/// LLM-backed endpoints (points/generate, ingest, finalize) can be slow on a
/// local zero-config model — mirror the Python client's generous timeout.
const HTTP_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(Debug, Clone)]
pub struct ApiConfig {
    pub base_url: String,
}

#[derive(Debug, Clone)]
pub struct Auth {
    /// JWT access token (the `access_token` field of the login response).
    pub token: String,
}

// ── Backend JSON shapes ────────────────────────────────────────────────────────

/// `WorkspaceOut`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub slug: String,
    pub created_at: String,
}

/// `MeetingOut`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meeting {
    pub id: String,
    pub workspace_id: String,
    pub title: String,
    pub purpose: Option<String>,
    /// "shadow" | "live_navigator" | "proxy" | "data_collection"
    pub mode: String,
    /// "draft" | "ready" | "in_progress" | "completed" | "cancelled"
    pub status: String,
    pub capture_level: i64,
    pub scheduled_at: Option<String>,
    pub started_at: Option<String>,
    pub ended_at: Option<String>,
    pub proxy_consent_given: bool,
    pub proxy_intro_logged: bool,
    pub meeting_url: Option<String>,
    pub calendar_event_id: Option<String>,
    pub auto_join_enabled: bool,
    pub created_at: String,
}

/// One speaking point (`_point_out` in the speak router).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Point {
    pub id: String,
    pub text: String,
    pub stage: String,
    /// "must" | "should" | "nice"
    pub priority: String,
    /// "pending" | "covered" | "missed"
    pub status: String,
    #[serde(default)]
    pub order_index: i64,
    #[serde(default)]
    pub covered_by_text: Option<String>,
}

/// A captured participant response attached to a point.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeakResponse {
    pub id: String,
    pub speaker: String,
    pub text: String,
    pub kind: String,
    pub point_id: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Progress {
    pub total: u32,
    pub covered: u32,
    pub missed: u32,
    pub pending: u32,
    pub must_remaining: u32,
}

/// Live memory nudge (`nudge_matcher.match_nudges`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Nudge {
    /// "promise" | "unanswered" | "conflict"
    pub kind: String,
    pub item_id: Option<String>,
    pub text: String,
    #[serde(default)]
    pub evidence: String,
}

/// Response of `/speak/state`, `/speak/points/generate` and `/speak/ingest`
/// (the latter adds `newly_covered` + `nudges`).
#[derive(Debug, Clone, Deserialize)]
pub struct SpeakState {
    #[serde(default)]
    pub points: Vec<Point>,
    #[serde(default)]
    pub responses: Vec<SpeakResponse>,
    #[serde(default)]
    pub progress: Progress,
    #[serde(default)]
    pub newly_covered: Vec<String>,
    #[serde(default)]
    pub nudges: Vec<Nudge>,
}

/// Response of `/speak/finalize`.
#[derive(Debug, Clone, Deserialize)]
pub struct WrapReport {
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub covered: Vec<String>,
    #[serde(default)]
    pub missed: Vec<String>,
    #[serde(default)]
    pub action_items: Vec<Value>,
    #[serde(default)]
    pub follow_ups: Vec<Value>,
    #[serde(default)]
    pub responses: Vec<Value>,
    #[serde(default)]
    pub report_id: Option<String>,
}

/// One transcript segment shipped to `/speak/ingest`.
#[derive(Debug, Clone, Serialize)]
pub struct Segment {
    pub speaker: String,
    pub text: String,
}

/// `UserOut` (returned by /api/auth/register).
#[derive(Debug, Clone, Deserialize)]
pub struct UserOut {
    pub id: String,
    pub email: String,
    pub full_name: String,
    pub is_active: bool,
    pub email_verified: bool,
    pub totp_enabled: bool,
    pub created_at: String,
}

// ── Low-level request plumbing ─────────────────────────────────────────────────

fn client() -> Result<reqwest::Client, CoreError> {
    Ok(reqwest::Client::builder().timeout(HTTP_TIMEOUT).build()?)
}

fn url(cfg: &ApiConfig, path: &str) -> String {
    format!("{}{}", cfg.base_url.trim_end_matches('/'), path)
}

async fn check<T: for<'de> Deserialize<'de>>(
    resp: reqwest::Response,
    path: &str,
) -> Result<T, CoreError> {
    let status = resp.status();
    if status.is_success() {
        return Ok(resp.json::<T>().await?);
    }
    let detail: String = resp
        .text()
        .await
        .unwrap_or_default()
        .chars()
        .take(300)
        .collect();
    if status.as_u16() == 401 || status.as_u16() == 403 {
        return Err(CoreError::Auth {
            path: path.to_string(),
            detail,
        });
    }
    Err(CoreError::Api {
        status: status.as_u16(),
        path: path.to_string(),
        detail,
    })
}

/// Authenticated call; JSON body optional. Public within the crate so the
/// engine can reuse the exact same policy for ingest/finalize.
pub(crate) async fn call<T: for<'de> Deserialize<'de>>(
    cfg: &ApiConfig,
    auth: &Auth,
    method: reqwest::Method,
    path: &str,
    body: Option<&Value>,
) -> Result<T, CoreError> {
    let mut req = client()?
        .request(method, url(cfg, path))
        .bearer_auth(&auth.token);
    if let Some(b) = body {
        req = req.json(b);
    }
    check(req.send().await?, path).await
}

// ── Public API ─────────────────────────────────────────────────────────────────

/// POST /api/auth/login → access token.
pub async fn login(cfg: &ApiConfig, email: &str, password: &str) -> Result<Auth, CoreError> {
    #[derive(Deserialize)]
    struct TokenResponse {
        access_token: String,
    }
    let path = "/api/auth/login";
    let resp = client()?
        .post(url(cfg, path))
        .json(&serde_json::json!({ "email": email, "password": password }))
        .send()
        .await?;
    let tok: TokenResponse = check(resp, path).await?;
    Ok(Auth {
        token: tok.access_token,
    })
}

/// POST /api/auth/register — convenience for provisioning (used by tests/CLI).
pub async fn register(
    cfg: &ApiConfig,
    email: &str,
    password: &str,
    full_name: &str,
) -> Result<UserOut, CoreError> {
    let path = "/api/auth/register";
    let resp = client()?
        .post(url(cfg, path))
        .json(&serde_json::json!({
            "email": email, "password": password, "full_name": full_name
        }))
        .send()
        .await?;
    check(resp, path).await
}

/// GET /api/workspaces
pub async fn list_workspaces(cfg: &ApiConfig, auth: &Auth) -> Result<Vec<Workspace>, CoreError> {
    call(cfg, auth, reqwest::Method::GET, "/api/workspaces", None).await
}

/// POST /api/workspaces
pub async fn create_workspace(
    cfg: &ApiConfig,
    auth: &Auth,
    name: &str,
) -> Result<Workspace, CoreError> {
    call(
        cfg,
        auth,
        reqwest::Method::POST,
        "/api/workspaces",
        Some(&serde_json::json!({ "name": name })),
    )
    .await
}

/// GET /api/workspaces/{workspace_id}/meetings
pub async fn list_meetings(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
) -> Result<Vec<Meeting>, CoreError> {
    let path = format!("/api/workspaces/{workspace_id}/meetings");
    call(cfg, auth, reqwest::Method::GET, &path, None).await
}

/// POST /api/workspaces/{workspace_id}/meetings
pub async fn create_meeting(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    title: &str,
) -> Result<Meeting, CoreError> {
    let path = format!("/api/workspaces/{workspace_id}/meetings");
    call(
        cfg,
        auth,
        reqwest::Method::POST,
        &path,
        Some(&serde_json::json!({ "title": title })),
    )
    .await
}

/// POST .../speak/points/generate — raw notes → prioritized speaking points.
pub async fn generate_points(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    meeting_id: &str,
    text: &str,
) -> Result<Vec<Point>, CoreError> {
    let path =
        format!("/api/workspaces/{workspace_id}/meetings/{meeting_id}/speak/points/generate");
    let state: SpeakState = call(
        cfg,
        auth,
        reqwest::Method::POST,
        &path,
        Some(&serde_json::json!({ "text": text })),
    )
    .await?;
    Ok(state.points)
}

/// GET .../speak/state
pub async fn get_speak_state(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    meeting_id: &str,
) -> Result<SpeakState, CoreError> {
    let path = format!("/api/workspaces/{workspace_id}/meetings/{meeting_id}/speak/state");
    call(cfg, auth, reqwest::Method::GET, &path, None).await
}

/// POST .../speak/ingest — ship a batch of transcript segments.
pub async fn speak_ingest(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    meeting_id: &str,
    segments: &[Segment],
) -> Result<SpeakState, CoreError> {
    let path = format!("/api/workspaces/{workspace_id}/meetings/{meeting_id}/speak/ingest");
    call(
        cfg,
        auth,
        reqwest::Method::POST,
        &path,
        Some(&serde_json::json!({ "segments": segments })),
    )
    .await
}

/// POST .../speak/finalize — close the session and get the wrap report.
pub async fn speak_finalize(
    cfg: &ApiConfig,
    auth: &Auth,
    workspace_id: &str,
    meeting_id: &str,
) -> Result<WrapReport, CoreError> {
    let path = format!("/api/workspaces/{workspace_id}/meetings/{meeting_id}/speak/finalize");
    call(cfg, auth, reqwest::Method::POST, &path, None).await
}
