//! The capture → STT → ingest engine.
//!
//! One background thread owns the whole pipeline (audio chunking, whisper
//! decode, batched HTTP) and reports everything through a channel of
//! [`EngineEvent`]s. All intelligence stays in the backend — this engine only
//! captures, transcribes and presents.

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tokio::sync::mpsc::{unbounded_channel, UnboundedReceiver, UnboundedSender};

use crate::api::{self, ApiConfig, Auth, Nudge, Point, Segment, SpeakState};
use crate::audio::{self, SAMPLE_RATE};
use crate::error::CoreError;
use crate::stt::Stt;

/// Mic capture chunk length (matches the Python prototype).
pub const CHUNK_SECONDS: f64 = 5.0;
/// Minimum interval between /speak/ingest batches.
pub const INGEST_EVERY: Duration = Duration::from_secs(4);
/// WAV files are decoded in whisper-native windows for best accuracy.
const WAV_WINDOW_SECONDS: f64 = 30.0;
/// A trailing mic chunk shorter than this on shutdown is discarded.
const MIN_TAIL_SECONDS: f64 = 0.5;
/// Everything captured on this machine is the owner's speech until the
/// system-audio ("Participants") stream lands in the platform layer.
const OWNER_SPEAKER: &str = "You";

#[derive(Debug, Clone)]
pub enum Source {
    /// Live microphone via cpal; `device` selects an input by name
    /// (substring match), `None` uses the default input device.
    Mic { device: Option<String> },
    /// Transcribe an audio file, then ingest — offline twin of the mic path.
    Wav { path: PathBuf },
}

#[derive(Debug, Clone)]
pub struct EngineConfig {
    pub api: ApiConfig,
    pub auth: Auth,
    pub workspace_id: String,
    pub meeting_id: String,
    pub source: Source,
    /// Path to a ggml whisper model (see [`crate::ensure_model`]).
    pub whisper_model: PathBuf,
    /// POST /speak/finalize (→ [`EngineEvent::Wrap`]) when the source ends
    /// or [`EngineHandle::stop`] is called.
    pub finalize_on_end: bool,
}

#[derive(Debug, Clone)]
pub enum EngineEvent {
    /// A locally transcribed utterance.
    Transcript {
        speaker: String,
        text: String,
    },
    /// Coverage progress after an ingest tick. `newly_covered` carries the
    /// ids of points that flipped to covered on this tick (match them
    /// against the accompanying [`EngineEvent::Points`] list).
    State {
        covered: u32,
        total: u32,
        must_remaining: u32,
        newly_covered: Vec<String>,
    },
    /// A live memory nudge, already deduplicated (each kind+item shown once).
    Nudge {
        kind: String,
        text: String,
        evidence: String,
    },
    /// Full point list with statuses, refreshed on every state update.
    Points {
        points: Vec<Point>,
    },
    /// Wrap report after finalize.
    Wrap {
        summary: String,
        covered: Vec<String>,
        missed: Vec<String>,
    },
    Error {
        message: String,
        fatal: bool,
    },
    /// Always the last event.
    Ended,
}

#[derive(Clone)]
pub struct EngineHandle {
    stop: Arc<AtomicBool>,
}

impl EngineHandle {
    /// Request a graceful shutdown: flush pending segments, finalize if
    /// configured, then emit [`EngineEvent::Ended`].
    pub fn stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}

/// Start the engine. Returns immediately; all progress (and all failures
/// after this point) arrives on the event channel.
pub fn start_engine(
    cfg: EngineConfig,
) -> Result<(EngineHandle, UnboundedReceiver<EngineEvent>), CoreError> {
    if !cfg.whisper_model.is_file() {
        return Err(CoreError::Config(format!(
            "whisper model not found: {}",
            cfg.whisper_model.display()
        )));
    }
    if let Source::Wav { path } = &cfg.source {
        if !path.is_file() {
            return Err(CoreError::Config(format!(
                "wav file not found: {}",
                path.display()
            )));
        }
    }

    let (tx, rx) = unbounded_channel();
    let stop = Arc::new(AtomicBool::new(false));
    let stop_flag = stop.clone();

    std::thread::Builder::new()
        .name("ammeet-engine".into())
        .spawn(move || run_engine(cfg, tx, stop_flag))
        .map_err(|e| CoreError::Config(format!("cannot spawn engine thread: {e}")))?;

    Ok((EngineHandle { stop }, rx))
}

// ── Nudge deduplication ────────────────────────────────────────────────────────

/// The backend repeats a nudge on later ticks while it stays relevant — the
/// engine surfaces each one exactly once (keyed like the Python client).
#[derive(Default)]
pub(crate) struct NudgeDedup {
    seen: HashSet<String>,
}

impl NudgeDedup {
    pub(crate) fn key(n: &Nudge) -> String {
        let ident = n.item_id.clone().unwrap_or_else(|| n.text.clone());
        format!("{}|{}", n.kind, ident)
    }

    /// Keep only nudges not seen before, remembering them.
    pub(crate) fn fresh(&mut self, nudges: Vec<Nudge>) -> Vec<Nudge> {
        nudges
            .into_iter()
            .filter(|n| self.seen.insert(Self::key(n)))
            .collect()
    }
}

// ── Engine internals ───────────────────────────────────────────────────────────

struct Engine {
    cfg: EngineConfig,
    tx: UnboundedSender<EngineEvent>,
    stop: Arc<AtomicBool>,
    rt: tokio::runtime::Runtime,
    pending: Vec<Segment>,
    dedup: NudgeDedup,
    last_send: Option<Instant>,
    /// Set once an unrecoverable (auth) error was emitted.
    dead: bool,
}

fn run_engine(cfg: EngineConfig, tx: UnboundedSender<EngineEvent>, stop: Arc<AtomicBool>) {
    let rt = match tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
    {
        Ok(rt) => rt,
        Err(e) => {
            let _ = tx.send(EngineEvent::Error {
                message: format!("tokio runtime: {e}"),
                fatal: true,
            });
            let _ = tx.send(EngineEvent::Ended);
            return;
        }
    };

    let mut engine = Engine {
        cfg,
        tx,
        stop,
        rt,
        pending: Vec::new(),
        dedup: NudgeDedup::default(),
        last_send: None,
        dead: false,
    };
    engine.run();
}

impl Engine {
    fn emit(&self, event: EngineEvent) {
        let _ = self.tx.send(event);
    }

    fn stopped(&self) -> bool {
        self.stop.load(Ordering::SeqCst)
    }

    fn run(&mut self) {
        let stt = match Stt::load(&self.cfg.whisper_model) {
            Ok(s) => s,
            Err(e) => {
                self.emit(EngineEvent::Error {
                    message: e.to_string(),
                    fatal: true,
                });
                self.emit(EngineEvent::Ended);
                return;
            }
        };

        match self.cfg.source.clone() {
            Source::Wav { path } => self.run_wav(&stt, &path),
            Source::Mic { device } => self.run_mic(&stt, device.as_deref()),
        }

        self.shutdown();
    }

    /// Transcribe a chunk, emit transcript events, queue for ingest, and
    /// flush on cadence.
    fn process_chunk(&mut self, stt: &Stt, samples: &[f32]) {
        if !audio::is_speech(samples) {
            return;
        }
        match stt.transcribe(samples) {
            Ok(texts) => {
                for text in texts {
                    self.emit(EngineEvent::Transcript {
                        speaker: OWNER_SPEAKER.to_string(),
                        text: text.clone(),
                    });
                    self.pending.push(Segment {
                        speaker: OWNER_SPEAKER.to_string(),
                        text,
                    });
                }
                self.maybe_flush(false);
            }
            Err(e) => self.emit(EngineEvent::Error {
                message: e.to_string(),
                fatal: false,
            }),
        }
    }

    fn run_wav(&mut self, stt: &Stt, path: &std::path::Path) {
        let samples = match audio::load_wav_16k_mono(path) {
            Ok(s) => s,
            Err(e) => {
                self.emit(EngineEvent::Error {
                    message: e.to_string(),
                    fatal: true,
                });
                return;
            }
        };
        let window = (WAV_WINDOW_SECONDS * SAMPLE_RATE as f64) as usize;
        for chunk in samples.chunks(window) {
            if self.stopped() || self.dead {
                break;
            }
            self.process_chunk(stt, chunk);
        }
    }

    fn run_mic(&mut self, stt: &Stt, device_name: Option<&str>) {
        use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

        let host = cpal::default_host();
        let device = match device_name {
            Some(name) => host.input_devices().ok().and_then(|mut devs| {
                devs.find(|d| {
                    d.name()
                        .map(|n| n.to_lowercase().contains(&name.to_lowercase()))
                        .unwrap_or(false)
                })
            }),
            None => host.default_input_device(),
        };
        let Some(device) = device else {
            self.emit(EngineEvent::Error {
                message: match device_name {
                    Some(n) => format!("no input device matching {n:?}"),
                    None => "no default input device".to_string(),
                },
                fatal: true,
            });
            return;
        };

        let config = match device.default_input_config() {
            Ok(c) => c,
            Err(e) => {
                self.emit(EngineEvent::Error {
                    message: format!("input config: {e}"),
                    fatal: true,
                });
                return;
            }
        };
        let native_rate = config.sample_rate().0;
        let channels = config.channels();
        let buffer: Arc<Mutex<Vec<f32>>> = Arc::new(Mutex::new(Vec::new()));
        let cb_buffer = buffer.clone();
        let err_tx = self.tx.clone();

        let stream = match config.sample_format() {
            cpal::SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _| cb_buffer.lock().unwrap().extend_from_slice(data),
                move |e| {
                    let _ = err_tx.send(EngineEvent::Error {
                        message: format!("mic stream: {e}"),
                        fatal: false,
                    });
                },
                None,
            ),
            cpal::SampleFormat::I16 => device.build_input_stream(
                &config.into(),
                move |data: &[i16], _| {
                    let mut buf = cb_buffer.lock().unwrap();
                    buf.extend(data.iter().map(|&s| s as f32 / i16::MAX as f32));
                },
                move |e| {
                    let _ = err_tx.send(EngineEvent::Error {
                        message: format!("mic stream: {e}"),
                        fatal: false,
                    });
                },
                None,
            ),
            other => {
                self.emit(EngineEvent::Error {
                    message: format!("unsupported mic sample format: {other:?}"),
                    fatal: true,
                });
                return;
            }
        };
        let stream = match stream {
            Ok(s) => s,
            Err(e) => {
                self.emit(EngineEvent::Error {
                    message: format!("cannot open mic stream: {e}"),
                    fatal: true,
                });
                return;
            }
        };
        if let Err(e) = stream.play() {
            self.emit(EngineEvent::Error {
                message: format!("cannot start mic stream: {e}"),
                fatal: true,
            });
            return;
        }

        let frames_per_chunk = (CHUNK_SECONDS * native_rate as f64) as usize * channels as usize;
        loop {
            if self.stopped() || self.dead {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
            let take = {
                let mut buf = buffer.lock().unwrap();
                if buf.len() >= frames_per_chunk {
                    Some(std::mem::take(&mut *buf))
                } else {
                    None
                }
            };
            if let Some(raw) = take {
                let mono = audio::downmix(&raw, channels);
                let chunk = audio::resample(&mono, native_rate, SAMPLE_RATE);
                self.process_chunk(stt, &chunk);
            }
        }
        drop(stream);

        // Drain whatever was captured after the last full chunk.
        let raw = std::mem::take(&mut *buffer.lock().unwrap());
        let min_tail = (MIN_TAIL_SECONDS * native_rate as f64) as usize * channels as usize;
        if raw.len() >= min_tail && !self.dead {
            let mono = audio::downmix(&raw, channels);
            let chunk = audio::resample(&mono, native_rate, SAMPLE_RATE);
            self.process_chunk(stt, &chunk);
        }
    }

    // ── Ingest / finalize ──────────────────────────────────────────────────────

    /// Flush queued segments to /speak/ingest, respecting the cadence unless
    /// forced. Transient failures retry once, then surface a non-fatal error
    /// (the batch is kept for the next flush). Auth failures kill the engine.
    fn maybe_flush(&mut self, force: bool) {
        if self.pending.is_empty() || self.dead {
            return;
        }
        if !force {
            if let Some(last) = self.last_send {
                if last.elapsed() < INGEST_EVERY {
                    return;
                }
            }
        }
        let segments = std::mem::take(&mut self.pending);
        self.last_send = Some(Instant::now());

        let cfg = &self.cfg;
        let result = self.rt.block_on(with_retry(|| {
            api::speak_ingest(
                &cfg.api,
                &cfg.auth,
                &cfg.workspace_id,
                &cfg.meeting_id,
                &segments,
            )
        }));

        match result {
            Ok(state) => self.emit_state(state),
            Err(e) if e.is_auth() => {
                self.emit(EngineEvent::Error {
                    message: e.to_string(),
                    fatal: true,
                });
                self.dead = true;
            }
            Err(e) => {
                // Keep the batch so the words are not lost; retry next tick.
                let mut kept = segments;
                kept.append(&mut self.pending);
                self.pending = kept;
                self.emit(EngineEvent::Error {
                    message: e.to_string(),
                    fatal: false,
                });
            }
        }
    }

    fn emit_state(&mut self, state: SpeakState) {
        self.emit(EngineEvent::State {
            covered: state.progress.covered,
            total: state.progress.total,
            must_remaining: state.progress.must_remaining,
            newly_covered: state.newly_covered.clone(),
        });
        self.emit(EngineEvent::Points {
            points: state.points,
        });
        for n in self.dedup.fresh(state.nudges) {
            self.emit(EngineEvent::Nudge {
                kind: n.kind,
                text: n.text,
                evidence: n.evidence,
            });
        }
    }

    fn shutdown(&mut self) {
        self.maybe_flush(true);
        if self.cfg.finalize_on_end && !self.dead {
            let cfg = &self.cfg;
            let result = self.rt.block_on(with_retry(|| {
                api::speak_finalize(&cfg.api, &cfg.auth, &cfg.workspace_id, &cfg.meeting_id)
            }));
            match result {
                Ok(report) => self.emit(EngineEvent::Wrap {
                    summary: report.summary,
                    covered: report.covered,
                    missed: report.missed,
                }),
                Err(e) => self.emit(EngineEvent::Error {
                    message: format!("finalize: {e}"),
                    fatal: false,
                }),
            }
        }
        self.emit(EngineEvent::Ended);
    }
}

/// Run a request; on a transient failure (transport error or 5xx) wait
/// briefly and retry exactly once. Auth and 4xx errors are not retried.
async fn with_retry<T, F, Fut>(mut op: F) -> Result<T, CoreError>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<T, CoreError>>,
{
    match op().await {
        Ok(v) => Ok(v),
        Err(e) if is_transient(&e) => {
            tokio::time::sleep(Duration::from_millis(500)).await;
            op().await
        }
        Err(e) => Err(e),
    }
}

fn is_transient(e: &CoreError) -> bool {
    match e {
        CoreError::Http(_) => true,
        CoreError::Api { status, .. } => *status >= 500,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn nudge(kind: &str, item_id: Option<&str>, text: &str) -> Nudge {
        Nudge {
            kind: kind.into(),
            item_id: item_id.map(String::from),
            text: text.into(),
            evidence: String::new(),
        }
    }

    #[test]
    fn nudge_dedup_matches_python_client_semantics() {
        let mut d = NudgeDedup::default();

        // First appearance passes through.
        let fresh = d.fresh(vec![nudge("promise", Some("a1"), "send the deck")]);
        assert_eq!(fresh.len(), 1);

        // Same kind+item_id repeats (even with different wording) → suppressed.
        let fresh = d.fresh(vec![nudge(
            "promise",
            Some("a1"),
            "you said you'd send the deck",
        )]);
        assert!(fresh.is_empty());

        // Same item, different kind → new.
        let fresh = d.fresh(vec![nudge("conflict", Some("a1"), "send the deck")]);
        assert_eq!(fresh.len(), 1);

        // No item_id → keyed by text.
        let fresh = d.fresh(vec![
            nudge("unanswered", None, "what about pricing?"),
            nudge("unanswered", None, "what about pricing?"),
            nudge("unanswered", None, "what about the timeline?"),
        ]);
        assert_eq!(fresh.len(), 2);
        let fresh = d.fresh(vec![nudge("unanswered", None, "what about pricing?")]);
        assert!(fresh.is_empty());
    }

    #[test]
    fn transient_classification() {
        assert!(is_transient(&CoreError::Api {
            status: 502,
            path: "/x".into(),
            detail: String::new()
        }));
        assert!(!is_transient(&CoreError::Api {
            status: 404,
            path: "/x".into(),
            detail: String::new()
        }));
        assert!(!is_transient(&CoreError::Auth {
            path: "/x".into(),
            detail: String::new()
        }));
    }
}
