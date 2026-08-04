# ammeet-core

The Rust core of the AmMeeting Phase-2 desktop app: **capture → local STT →
the existing backend Speak engine**, surfaced as a typed event stream.

One brain, many bodies: this crate adds capture and presentation only. All
intelligence (point generation, coverage matching, nudges, wrap summaries)
stays in the FastAPI backend — this is the Rust twin of the Python prototype
`desktop/ammeet_capture.py`, built to sit underneath the Tauri shell
(`../src-tauri` depends on it by path and forwards `EngineEvent`s to the
webview).

## What it does

- **Capture** — microphone via cpal (5 s chunks) or a WAV file via hound
  (decoded in 30 s whisper-native windows). Everything is resampled to
  16 kHz mono f32.
- **VAD** — a simple energy gate: chunks whose mean absolute amplitude is
  below `VAD_MEAN_ABS_THRESHOLD` (0.005) are skipped as silence. This is
  honest-but-basic; a real Silero-VAD (ONNX) gate is a planned upgrade and
  will slot in at the same point in the pipeline.
- **STT** — whisper.cpp via `whisper-rs`, CPU, greedy decoding. Language
  defaults to `en`, overridable with `AMMEET_STT_LANGUAGE`.
- **Ingest** — transcribed segments are batched and POSTed to
  `/speak/ingest` at most every 4 s; responses become `State` / `Points` /
  `Nudge` events (nudges deduplicated by `kind|item_id-or-text`, same as the
  Python client). On stop, pending segments are flushed and — with
  `finalize_on_end` — `/speak/finalize` produces a `Wrap` event.
- **Errors** — transient HTTP failures retry once, then surface as
  `Error { fatal: false }` (the batch is kept and retried on the next
  flush). Auth failures are `Error { fatal: true }` followed by `Ended`.

## Public API (sketch)

```rust
pub struct ApiConfig { pub base_url: String }
pub struct Auth { pub token: String }

pub async fn login(cfg, email, password) -> Result<Auth, CoreError>;
pub async fn register(cfg, email, password, full_name) -> Result<UserOut, CoreError>;
pub async fn list_workspaces(cfg, auth) -> Result<Vec<Workspace>, CoreError>;
pub async fn create_workspace(cfg, auth, name) -> Result<Workspace, CoreError>;
pub async fn list_meetings(cfg, auth, workspace_id) -> Result<Vec<Meeting>, CoreError>;
pub async fn create_meeting(cfg, auth, workspace_id, title) -> Result<Meeting, CoreError>;
pub async fn generate_points(cfg, auth, workspace_id, meeting_id, text) -> Result<Vec<Point>, CoreError>;
pub async fn get_speak_state(cfg, auth, workspace_id, meeting_id) -> Result<SpeakState, CoreError>;
pub async fn speak_ingest(cfg, auth, workspace_id, meeting_id, segments) -> Result<SpeakState, CoreError>;
pub async fn speak_finalize(cfg, auth, workspace_id, meeting_id) -> Result<WrapReport, CoreError>;

pub enum Source { Mic { device: Option<String> }, Wav { path: PathBuf } }
pub struct EngineConfig { api, auth, workspace_id, meeting_id, source, whisper_model, finalize_on_end }
pub enum EngineEvent {
    Transcript { speaker, text },
    State { covered, total, must_remaining, newly_covered },   // newly_covered = point ids
    Nudge { kind, text, evidence },
    Points { points: Vec<Point> },                             // full list on every state refresh
    Wrap { summary, covered, missed },
    Error { message, fatal },
    Ended,                                                     // always the last event
}
pub fn start_engine(cfg) -> Result<(EngineHandle, UnboundedReceiver<EngineEvent>), CoreError>;
impl EngineHandle { pub fn stop(&self); }   // graceful: flush → optional finalize → Ended

pub async fn ensure_model(dir, name) -> Result<PathBuf, CoreError>;
```

All JSON shapes (`Workspace`, `Meeting`, `Point`, `SpeakState`, `Nudge`,
`WrapReport`, …) mirror the backend responses field-for-field.

## Whisper models

`ensure_model(dir, name)` downloads
`https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin`
into `dir` if absent (streamed to a `.part` file, then renamed — no
half-written models). Sizes: `tiny.en` ≈ 78 MB (used by the tests),
`base.en` ≈ 148 MB, `small` ≈ 488 MB — **`small` is the recommended default
for real meetings**; `tiny.en` is for fast tests and smoke runs.

## CLI

`ammeet-core-cli` is the terminal twin of the Python prototype, useful for
verifying the pipeline without the Tauri shell:

```sh
cargo run --bin ammeet-core-cli -- \
  --api http://localhost:8010 \
  --email you@example.com \            # password via $AMMEET_PASSWORD, --password, or prompt
  --workspace-id WS --meeting-id MTG \
  --wav ../testdata-jfk.wav \          # or --mic [--device NAME]
  --model-dir models --model tiny.en \
  --finalize
```

It prints every `EngineEvent` as a `[tagged]` line; Ctrl-C stops gracefully
(flush + optional finalize). `--token` skips login.

## Tests

```sh
cargo test          # unit tests + live integration test
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

The integration test (`tests/live_backend.rs`) runs the **full pipeline
against the real local backend** at `http://localhost:8010`: it registers a
throwaway account, creates a workspace/meeting, generates speaking points
from a JFK-flavoured agenda, runs the engine over `../testdata-jfk.wav`
with `ggml-tiny.en` (cached in `target/models/`), and asserts on the
Transcript/State/Wrap events. It is **not** `#[ignore]`d — it only skips
(with a loud eprintln) when the backend is unreachable.

## Building on arm64 hosts (GCC quirk)

ggml's `-mcpu=native` probing generates
`-mcpu=native+nodotprod+noi8mm+nosve`, a spelling GCC (≤ 13) rejects,
which kills the `whisper-rs-sys` cmake build on arm64 Linux (e.g. this DGX
Spark / Grace box). The fix lives in this crate:

- `cmake/ggml-arm64-host.cmake` forces `GGML_NATIVE=OFF` and pins
  `GGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16` (GCC-friendly, keeps the hot
  loops vectorized);
- `.cargo/config.toml` injects it via the `CMAKE_TOOLCHAIN_FILE` env var,
  which the `cmake` crate forwards to the whisper.cpp configure.

Cargo only reads that config when building from inside `core/`. A sibling
crate (e.g. `src-tauri`) that depends on this crate by path must copy the
`[env]` entry into its own `.cargo/config.toml` (or export
`CMAKE_TOOLCHAIN_FILE` itself). x86_64 hosts are unaffected. If you hit a
stale-cache variant of the error after changing this, delete
`target/*/build/whisper-rs-sys-*` and rebuild.

## Honest limitations

- **Mic audio is tagged `"You"` only.** System-audio capture — the
  `"Participants"` stream (ScreenCaptureKit / WASAPI loopback / PipeWire
  monitor) — is the `src-tauri`/platform milestone, not part of this crate.
- The VAD is an energy gate, not a speech detector: it skips silence but
  passes any loud non-speech; Silero VAD is the planned replacement.
- WAV decoding is windowed (30 s), not word-aligned; a word can straddle a
  window boundary on long files.
- Whisper runs greedy on CPU; no diarization, no timestamps in events.
- `stop()` is graceful but synchronous with chunk boundaries: the engine
  notices the flag between chunks (≤ ~5 s latency on mic; between windows
  on WAV).
