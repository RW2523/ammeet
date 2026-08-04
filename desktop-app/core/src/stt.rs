//! Local speech-to-text via whisper.cpp (whisper-rs bindings, CPU, greedy).

use std::path::Path;
use std::sync::Once;

use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

use crate::audio::SAMPLE_RATE;
use crate::error::CoreError;

/// whisper.cpp rejects buffers shorter than ~1 s; pad up to this.
const MIN_SAMPLES: usize = (SAMPLE_RATE as usize) * 11 / 10; // 1.1 s

static LOG_HOOKS: Once = Once::new();

pub struct Stt {
    ctx: WhisperContext,
    language: String,
    n_threads: i32,
}

impl Stt {
    /// Load a ggml model from disk. `language` defaults to "en", overridable
    /// via the `AMMEET_STT_LANGUAGE` env var.
    pub fn load(model_path: &Path) -> Result<Self, CoreError> {
        // Route whisper.cpp's chatty stderr output into the `log` crate
        // (silent unless a logger is installed).
        LOG_HOOKS.call_once(whisper_rs::install_logging_hooks);

        if !model_path.is_file() {
            return Err(CoreError::Stt(format!(
                "whisper model not found: {}",
                model_path.display()
            )));
        }
        let path = model_path
            .to_str()
            .ok_or_else(|| CoreError::Stt("model path is not valid UTF-8".into()))?;
        let ctx = WhisperContext::new_with_params(path, WhisperContextParameters::default())
            .map_err(|e| CoreError::Stt(format!("failed to load model: {e}")))?;
        let language = std::env::var("AMMEET_STT_LANGUAGE").unwrap_or_else(|_| "en".to_string());
        let n_threads = std::thread::available_parallelism()
            .map(|n| n.get().min(8) as i32)
            .unwrap_or(4);
        Ok(Self {
            ctx,
            language,
            n_threads,
        })
    }

    /// Transcribe one chunk of 16 kHz mono f32 audio into text segments.
    pub fn transcribe(&self, samples: &[f32]) -> Result<Vec<String>, CoreError> {
        let mut padded;
        let audio = if samples.len() < MIN_SAMPLES {
            padded = samples.to_vec();
            padded.resize(MIN_SAMPLES, 0.0);
            &padded[..]
        } else {
            samples
        };

        let mut state = self
            .ctx
            .create_state()
            .map_err(|e| CoreError::Stt(format!("create_state: {e}")))?;
        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        params.set_language(Some(&self.language));
        params.set_n_threads(self.n_threads);
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params.set_suppress_blank(true);

        state
            .full(params, audio)
            .map_err(|e| CoreError::Stt(format!("decode: {e}")))?;

        let n = state
            .full_n_segments()
            .map_err(|e| CoreError::Stt(format!("segments: {e}")))?;
        let mut out = Vec::new();
        for i in 0..n {
            let text = state
                .full_get_segment_text_lossy(i)
                .map_err(|e| CoreError::Stt(format!("segment {i}: {e}")))?;
            let text = text.trim().to_string();
            // Whisper emits bracketed non-speech tokens on noise, e.g.
            // "[BLANK_AUDIO]", "(music)" — drop those.
            if !text.is_empty() && !is_non_speech_marker(&text) {
                out.push(text);
            }
        }
        Ok(out)
    }
}

fn is_non_speech_marker(text: &str) -> bool {
    let t = text.trim();
    (t.starts_with('[') && t.ends_with(']'))
        || (t.starts_with('(') && t.ends_with(')'))
        || (t.starts_with('*') && t.ends_with('*'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn non_speech_markers_are_detected() {
        assert!(is_non_speech_marker("[BLANK_AUDIO]"));
        assert!(is_non_speech_marker("(door slams)"));
        assert!(is_non_speech_marker("*music*"));
        assert!(!is_non_speech_marker("ask what you can do"));
    }
}
