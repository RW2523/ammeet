//! AmMeeting desktop shell — Tauri 2 tray app with a settings window and an
//! always-on-top Speak overlay. All meeting intelligence lives in the backend;
//! capture/engine work lives in the `ammeet-core` crate. This crate is only
//! shell: windows, tray, hotkey, command plumbing, event fan-out.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod config;
mod core_api;
mod events;
mod session;
mod state;
mod window_ctl;

use state::AppState;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::Manager;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            commands::login,
            commands::get_config,
            commands::list_workspaces,
            commands::list_meetings,
            commands::create_meeting,
            commands::generate_points,
            commands::pick_model,
            commands::start_session,
            commands::stop_session,
            commands::toggle_overlay,
            commands::show_settings,
            commands::quit,
        ])
        // Closing either window hides it; the tray owns the app lifecycle.
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                window_ctl::update_activation_policy(window.app_handle());
            }
        })
        .setup(|app| {
            // ── Managed state (config loaded from the OS app-config dir) ──
            let config_dir = app.path().app_config_dir()?;
            let cfg = config::load(&config_dir);
            app.manage(AppState::new(config_dir, cfg));

            // ── Tray icon + menu ──
            let show_settings =
                MenuItem::with_id(app, "show_settings", "Show Settings", true, None::<&str>)?;
            let toggle_overlay =
                MenuItem::with_id(app, "toggle_overlay", "Toggle Overlay", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit AmMeeting", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_settings, &toggle_overlay, &quit])?;

            // Icon embedded from our generated placeholder so the tray works
            // on every platform (config icons are not embedded on macOS).
            let tray_icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))?;
            TrayIconBuilder::with_id("ammeet-tray")
                .icon(tray_icon)
                .tooltip("AmMeeting")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show_settings" => window_ctl::show_settings(app),
                    "toggle_overlay" => window_ctl::toggle_overlay(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            // ── Global hotkey: ⌘⌥S on macOS, Ctrl+Alt+S elsewhere ──
            #[cfg(target_os = "macos")]
            let mods = Modifiers::SUPER | Modifiers::ALT;
            #[cfg(not(target_os = "macos"))]
            let mods = Modifiers::CONTROL | Modifiers::ALT;
            let toggle = Shortcut::new(Some(mods), Code::KeyS);
            app.global_shortcut().on_shortcut(toggle, |app, _sc, ev| {
                if ev.state == ShortcutState::Pressed {
                    window_ctl::toggle_overlay(app);
                }
            })?;

            // Settings is visible at launch → Regular policy on macOS.
            window_ctl::update_activation_policy(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building AmMeeting");

    app.run(|_app_handle, event| {
        // Keep running as a tray app when all windows are hidden/closed;
        // only an explicit `app.exit(0)` (tray Quit / `quit` command) exits.
        if let tauri::RunEvent::ExitRequested { code, api, .. } = &event {
            if code.is_none() {
                api.prevent_exit();
            }
        }
    });
}
