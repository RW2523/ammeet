//! Crate-wide error type.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum CoreError {
    /// Transport-level HTTP failure (connect, timeout, TLS ...).
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),

    /// The backend answered with a non-success status.
    #[error("api error {status} on {path}: {detail}")]
    Api {
        status: u16,
        path: String,
        detail: String,
    },

    /// 401/403 — the token is missing, expired or lacks the role.
    #[error("authentication failed on {path}: {detail}")]
    Auth { path: String, detail: String },

    #[error("audio error: {0}")]
    Audio(String),

    #[error("stt error: {0}")]
    Stt(String),

    #[error("model download error: {0}")]
    Model(String),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("invalid configuration: {0}")]
    Config(String),
}

impl CoreError {
    /// True for errors that cannot be retried away (bad credentials / roles).
    pub fn is_auth(&self) -> bool {
        matches!(self, CoreError::Auth { .. })
    }
}
