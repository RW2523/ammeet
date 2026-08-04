//! Persisted app configuration — pure serde types + load/save helpers.
//!
//! Deliberately free of tauri types so it can be unit-tested anywhere
//! (including on machines where the tauri crates cannot compile).

use serde::{Deserialize, Serialize};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// Default backend the settings window is pre-filled with.
pub const DEFAULT_BASE_URL: &str = "https://spark-9f46.tail1917c3.ts.net:8443";

/// File name inside the OS app-config directory (e.g.
/// `~/Library/Application Support/com.ammeet.desktop/` on macOS).
pub const CONFIG_FILE: &str = "config.json";

/// Everything we persist between launches. Auth tokens are intentionally NOT
/// persisted — the user logs in per app run (Phase-2 skeleton scope).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AppConfig {
    /// Backend base URL, no trailing slash.
    pub base_url: String,
    /// Last-used login email (convenience prefill only).
    pub email: String,
    /// Last-selected whisper model name (`tiny.en` / `base.en` / `small`).
    pub whisper_model: String,
    /// Optional override for where whisper models are stored.
    pub model_dir: Option<String>,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            base_url: DEFAULT_BASE_URL.to_string(),
            email: String::new(),
            whisper_model: "base.en".to_string(),
            model_dir: None,
        }
    }
}

pub fn config_path(dir: &Path) -> PathBuf {
    dir.join(CONFIG_FILE)
}

/// Load config from `dir`, falling back to defaults on any error
/// (missing file, unreadable JSON, …). Never fails.
pub fn load(dir: &Path) -> AppConfig {
    fs::read_to_string(config_path(dir))
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

/// Persist config to `dir/config.json`, creating the directory if needed.
pub fn save(dir: &Path, cfg: &AppConfig) -> io::Result<()> {
    fs::create_dir_all(dir)?;
    let raw = serde_json::to_string_pretty(cfg).map_err(io::Error::other)?;
    fs::write(config_path(dir), raw)
}

/// Normalize a user-typed backend URL: trim whitespace and trailing slashes.
pub fn normalize_base_url(input: &str) -> String {
    input.trim().trim_end_matches('/').to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("ammeet-desktop-test-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn defaults_are_sane() {
        let cfg = AppConfig::default();
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        assert_eq!(cfg.whisper_model, "base.en");
        assert!(cfg.email.is_empty());
        assert!(cfg.model_dir.is_none());
    }

    #[test]
    fn load_missing_file_returns_defaults() {
        let dir = tmp_dir("missing");
        assert_eq!(load(&dir), AppConfig::default());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let dir = tmp_dir("roundtrip");
        let cfg = AppConfig {
            base_url: "https://example.test:8443".into(),
            email: "a@b.c".into(),
            whisper_model: "tiny.en".into(),
            model_dir: Some("/models".into()),
        };
        save(&dir, &cfg).unwrap();
        assert_eq!(load(&dir), cfg);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn corrupt_file_falls_back_to_defaults() {
        let dir = tmp_dir("corrupt");
        fs::create_dir_all(&dir).unwrap();
        fs::write(config_path(&dir), "{not json").unwrap();
        assert_eq!(load(&dir), AppConfig::default());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn partial_json_fills_missing_fields() {
        let dir = tmp_dir("partial");
        fs::create_dir_all(&dir).unwrap();
        fs::write(config_path(&dir), r#"{"email":"x@y.z"}"#).unwrap();
        let cfg = load(&dir);
        assert_eq!(cfg.email, "x@y.z");
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn normalize_base_url_strips() {
        assert_eq!(
            normalize_base_url("  https://h:1/  "),
            "https://h:1".to_string()
        );
        assert_eq!(normalize_base_url("https://h"), "https://h");
    }
}
