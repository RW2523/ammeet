//! Whisper ggml model management: download-on-demand with a local cache.

use std::path::{Path, PathBuf};

use tokio::io::AsyncWriteExt;

use crate::error::CoreError;

const HF_BASE: &str = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main";

/// Below this size the file is clearly not a real model (tiny.en is ~75 MiB);
/// treat it as a corrupt partial download and re-fetch.
const MIN_MODEL_BYTES: u64 = 1_000_000;

/// Ensure `ggml-{name}.bin` exists in `dir`, downloading it from the official
/// whisper.cpp HuggingFace repo if absent. Returns the model path.
///
/// `name` is e.g. "tiny.en", "base.en", "small" (the documented default for
/// real use), "medium".
pub async fn ensure_model(dir: &Path, name: &str) -> Result<PathBuf, CoreError> {
    let file_name = format!("ggml-{name}.bin");
    let path = dir.join(&file_name);

    if let Ok(meta) = tokio::fs::metadata(&path).await {
        if meta.is_file() && meta.len() >= MIN_MODEL_BYTES {
            return Ok(path);
        }
    }

    tokio::fs::create_dir_all(dir).await?;
    let url = format!("{HF_BASE}/{file_name}");
    let client = reqwest::Client::builder()
        // No global timeout: a 500 MB model on a slow link is legitimate.
        .connect_timeout(std::time::Duration::from_secs(30))
        .build()?;
    let mut resp = client.get(&url).send().await?;
    if !resp.status().is_success() {
        return Err(CoreError::Model(format!(
            "download of {url} failed with HTTP {}",
            resp.status()
        )));
    }

    // Stream to a temp file, then rename — a crashed download never leaves a
    // half-written file at the final path.
    let tmp = dir.join(format!("{file_name}.part"));
    let mut file = tokio::fs::File::create(&tmp).await?;
    let mut written: u64 = 0;
    while let Some(chunk) = resp.chunk().await? {
        file.write_all(&chunk).await?;
        written += chunk.len() as u64;
    }
    file.flush().await?;
    drop(file);

    if written < MIN_MODEL_BYTES {
        let _ = tokio::fs::remove_file(&tmp).await;
        return Err(CoreError::Model(format!(
            "download of {url} produced only {written} bytes"
        )));
    }
    tokio::fs::rename(&tmp, &path).await?;
    Ok(path)
}
