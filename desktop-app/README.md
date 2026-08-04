# AmMeeting Desktop (Phase 2)

Tauri 2 shell for the AmMeeting desktop app: a **tray app** with two windows —
a normal **settings** window and a frameless, transparent, always-on-top
**Speak overlay** (the checklist pill from
`docs/ARCHITECTURE-DESKTOP-AND-CLOUD-BOT.md` §1.6). All capture/STT/backend
work lives in the sibling crate **`core/`** (`ammeet-core`); all meeting
intelligence stays in the backend. This directory is only shell: windows,
tray, global hotkey, command plumbing, event fan-out, UI.

```
desktop-app/
├── core/        ← ammeet-core (engine + API client; built separately)
├── src-tauri/   ← Rust shell (this crate: ammeet-desktop)
│   ├── src/
│   │   ├── main.rs        tray, windows, global hotkey, builder
│   │   ├── commands.rs    all #[tauri::command]s
│   │   ├── state.rs       managed AppState + engine-event drain task
│   │   ├── session.rs     pure lifecycle FSM (unit-tested)
│   │   ├── config.rs      pure config persistence (unit-tested)
│   │   ├── events.rs      EngineEvent → tagged JSON payloads
│   │   ├── core_api.rs    the ONLY call-site of ammeet-core (see below)
│   │   └── window_ctl.rs  show/hide + macOS activation policy
│   ├── capabilities/default.json
│   ├── icons/             placeholder PNGs (regenerate: npm run gen-icons in ui/)
│   └── tauri.conf.json
└── ui/          ← Vite + React + TS single SPA for BOTH windows
    └── src/     routed by `?window=settings|overlay` query param
```

---

## Building

### Why you cannot build the Rust side on the DGX box

The authoring machine (aarch64 Linux) has **no webkit2gtk/gtk dev libraries
and no sudo**, so any `cargo build`/`cargo check` of a Tauri crate fails at
the `*-sys` build scripts. Don't fight it there. The Rust code was written
against **pinned crate versions** (`tauri =2.11.5`, `tauri-build =2.6.3`,
`tauri-plugin-global-shortcut =2.3.2`) using only documented APIs; the pure
modules (`config.rs`, `session.rs`) have unit tests that were run on the
authoring box, and `events.rs`/`core_api.rs` were type-checked there against a
mock of the ammeet-core contract. Everything touching `tauri::*` compiles for
the first time on your Mac (or a provisioned Linux box).

### Linux prerequisites (one-time, needs sudo)

```sh
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev \
  build-essential curl wget file libssl-dev libxdo-dev
```

### macOS quickstart

1. **Xcode CLT + Rust + Node 20+**
   ```sh
   xcode-select --install
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
2. **Build the UI** (must be green before any cargo step):
   ```sh
   cd desktop-app/ui
   npm ci
   npm run build          # runs tsc --noEmit + vite build
   ```
3. **Tauri CLI + platform icons** (required before the first build — the
   bundle config lists `icon.icns`/`icon.ico`, which this generates from the
   committed placeholder PNG):
   ```sh
   cargo install tauri-cli --version "^2" --locked
   cd ../src-tauri
   cargo tauri icon icons/icon.png
   ```
4. **Run / bundle:**
   ```sh
   cargo tauri dev        # dev app (starts vite via beforeDevCommand)
   cargo tauri build      # signed-unsigned .app + dmg in target/release/bundle
   ```

First run on macOS will ask for Microphone permission when a mic session
starts. The overlay's transparency uses `macOSPrivateApi: true` (private API —
fine for dev/direct distribution; revisit before Mac App Store submission).

### UI-only development (any machine, no Rust needed)

```sh
cd desktop-app/ui
npm run dev        # http://localhost:5173/?window=settings or ?window=overlay
```

Outside the Tauri shell all `invoke`s are disabled with a friendly error, so
you can iterate on layout/styling in a plain browser.

---

## Using the app

- **Tray menu:** Show Settings / Toggle Overlay / Quit. Closing a window only
  hides it; the tray owns the app lifecycle.
- **Global hotkey:** `⌘⌥S` (macOS) / `Ctrl+Alt+S` (Windows/Linux) toggles the
  overlay.
- **Settings window:** backend URL (default
  `https://spark-9f46.tail1917c3.ts.net:8443`) → login → pick workspace +
  meeting (or create one) → optionally paste notes and *Generate points* →
  choose source (microphone, or a WAV file for testing) and whisper model
  (`tiny.en`/`base.en`/`small`, downloaded on first use) → *Start session*.
- **Overlay:** drag by the header; the pill reads e.g. `3/7 · 1 must left`;
  collapse toggle shrinks it to just the pill. Expanded view: points
  checklist (✓ covered / ✕ missed / ● must-pending), live nudge feed (amber =
  promise, blue = unanswered, red = conflict; newest on top, max 5), last
  transcript line, and **Finish** — which stops + finalizes and shows the wrap
  (summary, covered/missed) inline.
- **Config file:** `<app-config-dir>/config.json`
  (macOS: `~/Library/Application Support/com.ammeet.desktop/config.json`).
  Stores base URL, email, model choice — never passwords or tokens.

---

## Command / event contract (shell ↔ UI)

All commands use snake_case argument keys. Errors are strings.

| Command | Args | Returns |
|---|---|---|
| `login` | `base_url, email, password` | `{ok, email, base_url}` |
| `get_config` | — | `{base_url, email, whisper_model, model_dir, logged_in, phase}` |
| `list_workspaces` | — | backend workspaces (JSON passthrough) |
| `list_meetings` | `workspace_id` | backend meetings (JSON passthrough) |
| `create_meeting` | `workspace_id, title` | created meeting |
| `generate_points` | `workspace_id, meeting_id, notes` | `Point[]` |
| `pick_model` | `name, dir?` | model path (emits `model://progress`) |
| `start_session` | `workspace_id, meeting_id, source, model?, finalize_on_end?` | `{ok}` |
| `stop_session` | — | `{ok, clean}` (waits ≤8 s for `Ended`) |
| `toggle_overlay` / `show_settings` / `quit` | — | — |

`source` is `{"type":"mic","device":string|null}` or
`{"type":"wav","path":string}`.

| Event | Payload |
|---|---|
| `engine://event` | every `EngineEvent`, tagged: `{type: "Transcript"\|"State"\|"Nudge"\|"Points"\|"Wrap"\|"Error"\|"Ended", …fields}` |
| `session://status` | `{phase: "not_logged_in"\|"idle"\|"starting"\|"running", workspace_id?, meeting_id?}` |
| `model://progress` | `{name, status: "preparing"\|"ready"\|"error", path?, message?}` |

Session lifecycle (managed `AppState`): `NotLoggedIn → Idle → Running → Idle`.
`stop_session` sends the engine a stop signal and waits (with timeout) for the
drain task to observe `Ended`; the drain task also cleans up on fatal errors
or channel close, so the FSM can never wedge in `Running`.

---

## Security notes

**CSP tradeoff (deliberate):** `connect-src` in `tauri.conf.json` allows
`https:` and `http:` wholesale because the backend URL is user-typed (self-
hosted deployments, tailnets, localhost). A locked-down build should replace
that with its known backend origin. Everything else stays `'self'`;
`'unsafe-inline'` is granted to styles only. The `ipc:`/`http://ipc.localhost`
entries are required by Tauri's IPC on Windows/Linux.

**Capabilities:** `capabilities/default.json` grants only core defaults plus
the window verbs the overlay needs (show/hide/is-visible/set-focus/
start-dragging/set-size) and global-shortcut introspection. No fs/shell/http
plugins — all network I/O happens in Rust inside `ammeet-core`.

---

## ammeet-core assumptions (read before first compile)

`src/core_api.rs` is the **only** module calling `ammeet-core` (plus
`events.rs`, which pattern-matches `EngineEvent`). The shared contract left
some signatures open; the assumptions — each a one-line local fix if the core
chose differently — are documented at the top of `core_api.rs`:
Result-returning async fns with Display errors; `&ApiConfig/&Auth/&str`
params in `(cfg, auth, workspace_id, meeting_id, …)` order; `Serialize` on
workspace/meeting list types; `ensure_model(&Path, &str)`;
`EngineConfig.whisper_model: PathBuf`; String ids; synchronous
`EngineHandle::stop()`. If the first `cargo build` against the real core
errors, fix it in `core_api.rs`/`events.rs` only — nothing else touches it.

## Known limitations / follow-ups

- Auth token is held in memory only; login is per app run (device-code flow
  is the Phase-2 target per the architecture doc).
- Overlay is not click-through outside interactive elements yet (§1.6);
  collapse-to-pill shrinks the window instead so stray clicks can't be eaten.
- `pick_model` progress is coarse (`preparing → ready`) because
  `ensure_model` exposes no byte-level progress.
- Placeholder icons: regenerate with `npm run gen-icons` (ui/), then
  `cargo tauri icon icons/icon.png` for platform formats.
