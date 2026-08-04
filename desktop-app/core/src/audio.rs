//! Audio utilities: WAV loading, resampling to the STT format, and the
//! energy-gate VAD.
//!
//! Everything downstream of capture works on 16 kHz mono f32 — the format
//! whisper.cpp expects.

use std::path::Path;

use crate::error::CoreError;

/// Sample rate whisper.cpp consumes.
pub const SAMPLE_RATE: u32 = 16_000;

/// Energy-gate VAD threshold: a chunk whose mean absolute amplitude (f32 in
/// [-1, 1]) is below this is treated as silence and skipped. 0.005 sits well
/// below normal speech (~0.02–0.1) and above mic noise floors (~0.001).
/// A real VAD (Silero ONNX) is a planned upgrade — see README.
pub const VAD_MEAN_ABS_THRESHOLD: f32 = 0.005;

/// True when the chunk carries enough energy to plausibly contain speech.
pub fn is_speech(samples: &[f32]) -> bool {
    if samples.is_empty() {
        return false;
    }
    let mean_abs = samples.iter().map(|s| s.abs()).sum::<f32>() / samples.len() as f32;
    mean_abs >= VAD_MEAN_ABS_THRESHOLD
}

/// Downmix interleaved multi-channel audio to mono by averaging channels.
pub fn downmix(samples: &[f32], channels: u16) -> Vec<f32> {
    if channels <= 1 {
        return samples.to_vec();
    }
    let ch = channels as usize;
    samples
        .chunks_exact(ch)
        .map(|frame| frame.iter().sum::<f32>() / ch as f32)
        .collect()
}

/// Linear-interpolation resampler (mono in, mono out). Good enough for
/// speech-to-text; not intended for playback fidelity.
pub fn resample(samples: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || samples.is_empty() {
        return samples.to_vec();
    }
    let ratio = from_rate as f64 / to_rate as f64;
    let out_len = ((samples.len() as f64) / ratio).floor() as usize;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let pos = i as f64 * ratio;
        let idx = pos as usize;
        let frac = (pos - idx as f64) as f32;
        let a = samples[idx];
        let b = *samples.get(idx + 1).unwrap_or(&a);
        out.push(a + (b - a) * frac);
    }
    out
}

/// Read a WAV file into 16 kHz mono f32, downmixing and resampling as needed.
/// Supports 16/24/32-bit integer PCM and 32-bit float WAVs.
pub fn load_wav_16k_mono(path: &Path) -> Result<Vec<f32>, CoreError> {
    let mut reader = hound::WavReader::open(path)
        .map_err(|e| CoreError::Audio(format!("cannot open {}: {e}", path.display())))?;
    let spec = reader.spec();

    let interleaved: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader
            .samples::<f32>()
            .collect::<Result<_, _>>()
            .map_err(|e| CoreError::Audio(format!("wav read: {e}")))?,
        hound::SampleFormat::Int => {
            let max = (1i64 << (spec.bits_per_sample - 1)) as f32;
            reader
                .samples::<i32>()
                .map(|s| s.map(|v| v as f32 / max))
                .collect::<Result<_, _>>()
                .map_err(|e| CoreError::Audio(format!("wav read: {e}")))?
        }
    };

    let mono = downmix(&interleaved, spec.channels);
    Ok(resample(&mono, spec.sample_rate, SAMPLE_RATE))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::TAU;

    fn tone(rate: u32, secs: f32, hz: f32, amp: f32) -> Vec<f32> {
        (0..(rate as f32 * secs) as usize)
            .map(|i| amp * (TAU * hz * i as f32 / rate as f32).sin())
            .collect()
    }

    #[test]
    fn vad_rejects_silence_and_accepts_tone() {
        let silence = vec![0.0f32; SAMPLE_RATE as usize];
        assert!(!is_speech(&silence));
        let near_silence = tone(SAMPLE_RATE, 1.0, 220.0, 0.001);
        assert!(!is_speech(&near_silence));
        let speechy = tone(SAMPLE_RATE, 1.0, 220.0, 0.1);
        assert!(is_speech(&speechy));
        assert!(!is_speech(&[]));
    }

    #[test]
    fn resample_halves_length_and_keeps_shape() {
        let src = tone(32_000, 1.0, 440.0, 0.5);
        let out = resample(&src, 32_000, 16_000);
        // Length within one sample of exactly half.
        assert!((out.len() as i64 - 16_000).abs() <= 1, "len={}", out.len());
        // Energy preserved (same tone, half rate — amplitude unchanged).
        assert!(is_speech(&out));
        // Identity path.
        let same = resample(&src, 16_000, 16_000);
        assert_eq!(same.len(), src.len());
    }

    #[test]
    fn wav_loader_resamples_stereo_44k_to_16k_mono() {
        let dir = std::env::temp_dir().join("ammeet-core-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("stereo44k.wav");

        let spec = hound::WavSpec {
            channels: 2,
            sample_rate: 44_100,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::create(&path, spec).unwrap();
        let mono = tone(44_100, 2.0, 440.0, 0.5);
        for s in &mono {
            let v = (s * i16::MAX as f32) as i16;
            writer.write_sample(v).unwrap(); // L
            writer.write_sample(v).unwrap(); // R
        }
        writer.finalize().unwrap();

        let samples = load_wav_16k_mono(&path).unwrap();
        let expected = 2 * SAMPLE_RATE as usize;
        let diff = samples.len() as i64 - expected as i64;
        assert!(
            diff.abs() <= 2,
            "expected ~{expected}, got {}",
            samples.len()
        );
        assert!(is_speech(&samples));
    }
}
