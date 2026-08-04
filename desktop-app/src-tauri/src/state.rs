//! Managed application state + the engine-event drain task.

use crate::config::AppConfig;
use crate::events;
use crate::session::SessionFsm;
use ammeet_core::{Auth, EngineEvent, EngineHandle};
use serde_json::json;
use std::path::PathBuf;
use std::sync::Arc;
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::mpsc::UnboundedReceiver;
use tokio::sync::{Mutex, Notify};

/// A live engine session.
pub struct RunningSession {
    pub handle: EngineHandle,
    /// Notified (with a stored permit) by the drain task once the engine has
    /// emitted `Ended` / a fatal `Error`, or the event channel closed.
    pub ended: Arc<Notify>,
}

pub struct Inner {
    pub fsm: SessionFsm,
    pub auth: Option<Auth>,
    pub config: AppConfig,
    pub config_dir: PathBuf,
    pub running: Option<RunningSession>,
}

/// Tauri-managed state. A single async Mutex keeps every phase/auth/handle
/// mutation serialized; commands never hold it across engine/API awaits.
pub struct AppState {
    pub inner: Mutex<Inner>,
}

impl AppState {
    pub fn new(config_dir: PathBuf, config: AppConfig) -> Self {
        Self {
            inner: Mutex::new(Inner {
                fsm: SessionFsm::new(),
                auth: None,
                config,
                config_dir,
                running: None,
            }),
        }
    }
}

/// Drain the engine's event channel, re-emitting every event to all windows as
/// `engine://event`. On session end (Ended / fatal Error / channel close):
/// flip the FSM back to Idle, drop the handle, broadcast an idle status, and
/// wake any `stop_session` waiter.
pub fn spawn_drain(app: AppHandle, mut rx: UnboundedReceiver<EngineEvent>, ended: Arc<Notify>) {
    tauri::async_runtime::spawn(async move {
        loop {
            match rx.recv().await {
                Some(ev) => {
                    let terminal = events::is_terminal(&ev);
                    let _ = app.emit(events::ENGINE_EVENT, events::engine_event_payload(&ev));
                    if terminal {
                        break;
                    }
                }
                None => break, // engine dropped the sender
            }
        }
        {
            let state = app.state::<AppState>();
            let mut inner = state.inner.lock().await;
            inner.running = None;
            inner.fsm.on_ended();
        }
        let _ = app.emit(events::SESSION_STATUS, json!({ "phase": "idle" }));
        // notify_one stores a permit, so a stop_session that starts waiting
        // *after* this line still returns immediately.
        ended.notify_one();
    });
}
