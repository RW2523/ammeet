//! Pure session-lifecycle state machine: NotLoggedIn → Idle → Running → Idle.
//!
//! The `EngineHandle` itself lives in [`crate::state`]; this module only owns
//! the phase transitions so they can be unit-tested without tauri or the core
//! crate.

use serde::Serialize;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    NotLoggedIn,
    Idle,
    Running,
}

impl Default for Phase {
    fn default() -> Self {
        Phase::NotLoggedIn
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StartError {
    NotLoggedIn,
    AlreadyRunning,
}

impl fmt::Display for StartError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StartError::NotLoggedIn => write!(f, "Not logged in"),
            StartError::AlreadyRunning => write!(f, "A session is already running"),
        }
    }
}

#[derive(Debug, Default)]
pub struct SessionFsm {
    phase: Phase,
}

impl SessionFsm {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn phase(&self) -> Phase {
        self.phase
    }

    /// Successful login: NotLoggedIn → Idle. No-op if already past login.
    pub fn on_login(&mut self) {
        if self.phase == Phase::NotLoggedIn {
            self.phase = Phase::Idle;
        }
    }

    /// Attempt to start a session: only legal from Idle.
    pub fn try_start(&mut self) -> Result<(), StartError> {
        match self.phase {
            Phase::NotLoggedIn => Err(StartError::NotLoggedIn),
            Phase::Running => Err(StartError::AlreadyRunning),
            Phase::Idle => {
                self.phase = Phase::Running;
                Ok(())
            }
        }
    }

    /// Engine ended (cleanly, fatally, or via stop): Running → Idle.
    /// Idempotent — safe to call from both the drain task and `stop_session`.
    pub fn on_ended(&mut self) {
        if self.phase == Phase::Running {
            self.phase = Phase::Idle;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_not_logged_in() {
        assert_eq!(SessionFsm::new().phase(), Phase::NotLoggedIn);
    }

    #[test]
    fn cannot_start_before_login() {
        let mut fsm = SessionFsm::new();
        assert_eq!(fsm.try_start(), Err(StartError::NotLoggedIn));
        assert_eq!(fsm.phase(), Phase::NotLoggedIn);
    }

    #[test]
    fn login_then_start_then_end() {
        let mut fsm = SessionFsm::new();
        fsm.on_login();
        assert_eq!(fsm.phase(), Phase::Idle);
        assert!(fsm.try_start().is_ok());
        assert_eq!(fsm.phase(), Phase::Running);
        fsm.on_ended();
        assert_eq!(fsm.phase(), Phase::Idle);
    }

    #[test]
    fn double_start_rejected() {
        let mut fsm = SessionFsm::new();
        fsm.on_login();
        assert!(fsm.try_start().is_ok());
        assert_eq!(fsm.try_start(), Err(StartError::AlreadyRunning));
        assert_eq!(fsm.phase(), Phase::Running);
    }

    #[test]
    fn on_ended_is_idempotent() {
        let mut fsm = SessionFsm::new();
        fsm.on_ended(); // no-op before login
        assert_eq!(fsm.phase(), Phase::NotLoggedIn);
        fsm.on_login();
        fsm.on_ended(); // no-op while idle
        assert_eq!(fsm.phase(), Phase::Idle);
        fsm.try_start().unwrap();
        fsm.on_ended();
        fsm.on_ended();
        assert_eq!(fsm.phase(), Phase::Idle);
    }

    #[test]
    fn login_is_idempotent_and_never_downgrades() {
        let mut fsm = SessionFsm::new();
        fsm.on_login();
        fsm.on_login();
        assert_eq!(fsm.phase(), Phase::Idle);
        fsm.try_start().unwrap();
        fsm.on_login(); // must not clobber Running
        assert_eq!(fsm.phase(), Phase::Running);
    }

    #[test]
    fn phase_serializes_snake_case() {
        assert_eq!(
            serde_json::to_string(&Phase::NotLoggedIn).unwrap(),
            "\"not_logged_in\""
        );
        assert_eq!(serde_json::to_string(&Phase::Idle).unwrap(), "\"idle\"");
        assert_eq!(
            serde_json::to_string(&Phase::Running).unwrap(),
            "\"running\""
        );
    }
}
