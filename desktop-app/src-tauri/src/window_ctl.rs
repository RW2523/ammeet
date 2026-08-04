//! Window show/hide helpers shared by tray menu, global hotkey, and commands.

use tauri::{AppHandle, Manager};

pub const SETTINGS_WINDOW: &str = "settings";
pub const OVERLAY_WINDOW: &str = "overlay";

pub fn show_settings(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(SETTINGS_WINDOW) {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    update_activation_policy(app);
}

/// Toggle the always-on-top overlay. Deliberately does NOT focus it — the
/// overlay floats over the user's meeting app and must not steal focus.
pub fn toggle_overlay(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(OVERLAY_WINDOW) {
        if w.is_visible().unwrap_or(false) {
            let _ = w.hide();
        } else {
            let _ = w.show();
        }
    }
    update_activation_policy(app);
}

/// macOS nicety: when only the overlay (or nothing) is visible, switch to the
/// Accessory activation policy so the app has no Dock icon and never steals
/// the ⌘-Tab switcher; give the Dock icon back while Settings is open.
#[cfg(target_os = "macos")]
pub fn update_activation_policy(app: &AppHandle) {
    use tauri::ActivationPolicy;
    let settings_visible = app
        .get_webview_window(SETTINGS_WINDOW)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false);
    let policy = if settings_visible {
        ActivationPolicy::Regular
    } else {
        ActivationPolicy::Accessory
    };
    let _ = app.set_activation_policy(policy);
}

#[cfg(not(target_os = "macos"))]
pub fn update_activation_policy(_app: &AppHandle) {}
