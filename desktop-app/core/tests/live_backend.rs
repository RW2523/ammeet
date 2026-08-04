//! Full-pipeline integration test against the REAL local backend
//! (http://localhost:8010, zero-config LLM behind it).
//!
//! Flow: register a throwaway account → workspace → meeting → generate
//! speaking points from a short agenda → run the engine over the JFK test
//! WAV with ggml-tiny.en → assert Transcript / State / Wrap events.
//!
//! Skips gracefully (with a loud eprintln) only when the backend is
//! unreachable; otherwise it must pass.

use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use ammeet_core::{
    create_meeting, create_workspace, ensure_model, generate_points, login, register, start_engine,
    ApiConfig, EngineConfig, EngineEvent, Source,
};

const BASE_URL: &str = "http://localhost:8010";

/// The agenda deliberately contains a point the JFK clip covers verbatim.
const AGENDA: &str = "Notes for my inaugural address:\n\
    - Open by acknowledging this is a celebration of freedom, not a victory of party.\n\
    - Urge people to ask what they can do for their country, not what their country can do for them.\n\
    - Close by asking the citizens of the world to work together for the freedom of man.";

async fn backend_reachable() -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    matches!(
        client.get(format!("{BASE_URL}/api/health")).send().await,
        Ok(resp) if resp.status().is_success()
    )
}

#[tokio::test(flavor = "multi_thread")]
async fn full_pipeline_against_live_backend() {
    if !backend_reachable().await {
        eprintln!("SKIP full_pipeline_against_live_backend: backend at {BASE_URL} is unreachable");
        return;
    }

    let cfg = ApiConfig {
        base_url: BASE_URL.to_string(),
    };

    // ── Provision a throwaway account + workspace + meeting ────────────────
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let email = format!("r4-core-{nonce}@example.com");
    let password = "R4core-Pass-w0rd";

    register(&cfg, &email, password, "R4 Core Test")
        .await
        .expect("register throwaway account");
    let auth = login(&cfg, &email, password).await.expect("login");

    let workspace = create_workspace(&cfg, &auth, "r4-core-test")
        .await
        .expect("create workspace");
    let meeting = create_meeting(&cfg, &auth, &workspace.id, "R4 core pipeline test")
        .await
        .expect("create meeting");

    let points = generate_points(&cfg, &auth, &workspace.id, &meeting.id, AGENDA)
        .await
        .expect("generate speaking points");
    assert!(
        !points.is_empty(),
        "backend derived no speaking points from the agenda"
    );
    eprintln!("generated {} points:", points.len());
    for p in &points {
        eprintln!("  [{}] {}", p.priority, p.text);
    }

    // ── Model + test audio ─────────────────────────────────────────────────
    let model_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/models");
    let model_path = ensure_model(&model_dir, "tiny.en")
        .await
        .expect("download/cache ggml-tiny.en");

    let wav = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../testdata-jfk.wav");
    assert!(wav.is_file(), "missing test audio at {}", wav.display());

    // ── Run the engine ─────────────────────────────────────────────────────
    let (_handle, mut rx) = start_engine(EngineConfig {
        api: cfg.clone(),
        auth,
        workspace_id: workspace.id.clone(),
        meeting_id: meeting.id.clone(),
        source: Source::Wav { path: wav },
        whisper_model: model_path,
        finalize_on_end: true,
    })
    .expect("start engine");

    let mut transcripts: Vec<String> = Vec::new();
    let mut max_covered = 0u32;
    let mut got_wrap = false;
    let mut got_ended = false;
    let mut fatal_errors: Vec<String> = Vec::new();

    let deadline = Duration::from_secs(600);
    let drain = async {
        while let Some(event) = rx.recv().await {
            match event {
                EngineEvent::Transcript { speaker, text } => {
                    eprintln!("event Transcript [{speaker}]: {text}");
                    transcripts.push(text);
                }
                EngineEvent::State {
                    covered,
                    total,
                    must_remaining,
                    ref newly_covered,
                } => {
                    eprintln!(
                        "event State: {covered}/{total} covered, {must_remaining} must left, newly {newly_covered:?}"
                    );
                    max_covered = max_covered.max(covered);
                }
                EngineEvent::Points { ref points } => {
                    eprintln!("event Points: {} points", points.len());
                }
                EngineEvent::Nudge {
                    ref kind, ref text, ..
                } => {
                    eprintln!("event Nudge [{kind}]: {text}");
                }
                EngineEvent::Wrap {
                    ref summary,
                    ref covered,
                    ref missed,
                } => {
                    eprintln!(
                        "event Wrap: summary={:?} covered={} missed={}",
                        summary,
                        covered.len(),
                        missed.len()
                    );
                    got_wrap = true;
                }
                EngineEvent::Error { ref message, fatal } => {
                    eprintln!("event Error (fatal={fatal}): {message}");
                    if fatal {
                        fatal_errors.push(message.clone());
                    }
                }
                EngineEvent::Ended => {
                    eprintln!("event Ended");
                    got_ended = true;
                    break;
                }
            }
        }
    };
    tokio::time::timeout(deadline, drain)
        .await
        .expect("engine did not finish within the deadline");

    // ── Assertions ─────────────────────────────────────────────────────────
    assert!(got_ended, "engine never emitted Ended");
    assert!(
        fatal_errors.is_empty(),
        "engine hit fatal errors: {fatal_errors:?}"
    );
    assert!(
        transcripts
            .iter()
            .any(|t| t.to_lowercase().contains("country")),
        "no Transcript event mentioned 'country'; got: {transcripts:?}"
    );
    assert!(
        max_covered >= 1,
        "no State event reported covered >= 1 (max was {max_covered})"
    );
    assert!(got_wrap, "no Wrap event despite finalize_on_end");
}
