//! Terminal twin of the desktop engine — the Rust counterpart of
//! `desktop/ammeet_capture.py`. Captures (mic or wav), transcribes locally,
//! streams to the backend Speak engine and prints every event.

use std::io::Write;
use std::path::PathBuf;

use clap::Parser;

use ammeet_core::{
    ensure_model, login, start_engine, ApiConfig, Auth, EngineConfig, EngineEvent, Source,
};

#[derive(Parser)]
#[command(
    name = "ammeet-core-cli",
    about = "AmMeeting desktop core CLI: capture -> local STT -> backend Speak engine"
)]
struct Args {
    /// Backend base URL, e.g. http://localhost:8010
    #[arg(long)]
    api: String,

    /// Login email (password from --password, $AMMEET_PASSWORD, or prompt)
    #[arg(long)]
    email: Option<String>,

    /// Password for --email (avoid on shared shells; prefer the env var)
    #[arg(long)]
    password: Option<String>,

    /// Access token (skips login)
    #[arg(long, conflicts_with = "email")]
    token: Option<String>,

    #[arg(long)]
    workspace_id: String,

    #[arg(long)]
    meeting_id: String,

    /// Transcribe an audio file, then ingest
    #[arg(long, conflicts_with = "mic")]
    wav: Option<PathBuf>,

    /// Live microphone capture
    #[arg(long)]
    mic: bool,

    /// Input device name for --mic (substring match; default input if omitted)
    #[arg(long)]
    device: Option<String>,

    /// Directory for whisper models (downloaded on demand)
    #[arg(long, default_value = "models")]
    model_dir: PathBuf,

    /// Whisper model name: tiny.en, base.en, small, medium ...
    #[arg(long, default_value = "small")]
    model: String,

    /// Finalize the Speak session when the source ends (prints the wrap)
    #[arg(long)]
    finalize: bool,
}

#[tokio::main]
async fn main() {
    if let Err(e) = run().await {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    let api = ApiConfig {
        base_url: args.api.clone(),
    };

    let auth = match (&args.token, &args.email) {
        (Some(token), _) => Auth {
            token: token.clone(),
        },
        (None, Some(email)) => {
            let password = match args.password.clone() {
                Some(p) => p,
                None => match std::env::var("AMMEET_PASSWORD") {
                    Ok(p) => p,
                    Err(_) => prompt_password()?,
                },
            };
            login(&api, email, &password).await?
        }
        (None, None) => return Err("--email or --token is required".into()),
    };

    let source = match &args.wav {
        Some(path) => Source::Wav { path: path.clone() },
        None if args.mic => Source::Mic {
            device: args.device.clone(),
        },
        None => return Err("--wav FILE or --mic is required".into()),
    };

    eprintln!(
        "model: ensuring ggml-{} in {} ...",
        args.model,
        args.model_dir.display()
    );
    let model_path = ensure_model(&args.model_dir, &args.model).await?;
    eprintln!("model: {}", model_path.display());

    let (handle, mut rx) = start_engine(EngineConfig {
        api,
        auth,
        workspace_id: args.workspace_id,
        meeting_id: args.meeting_id,
        source,
        whisper_model: model_path,
        finalize_on_end: args.finalize,
    })?;

    // Ctrl-C → graceful stop (flush + optional finalize), then Ended arrives.
    let stopper = handle.clone();
    tokio::spawn(async move {
        if tokio::signal::ctrl_c().await.is_ok() {
            eprintln!("\nstopping (flushing pending segments) ...");
            stopper.stop();
        }
    });

    while let Some(event) = rx.recv().await {
        print_event(&event);
        if matches!(event, EngineEvent::Ended) {
            break;
        }
    }
    Ok(())
}

fn print_event(event: &EngineEvent) {
    match event {
        EngineEvent::Transcript { speaker, text } => println!("[transcript] {speaker}: {text}"),
        EngineEvent::State {
            covered,
            total,
            must_remaining,
            newly_covered,
        } => {
            let newly = if newly_covered.is_empty() {
                String::new()
            } else {
                format!(" · newly covered: {}", newly_covered.join(", "))
            };
            println!("[state] {covered}/{total} covered · {must_remaining} must left{newly}");
        }
        EngineEvent::Nudge {
            kind,
            text,
            evidence,
        } => {
            let label = match kind.as_str() {
                "promise" => "YOU PROMISED",
                "unanswered" => "STILL UNANSWERED",
                "conflict" => "CONFLICTS WITH A DECISION",
                _ => "NUDGE",
            };
            println!("[nudge] {label}: {text} (evidence: {evidence})");
        }
        EngineEvent::Points { points } => {
            for p in points {
                let mark = match p.status.as_str() {
                    "covered" => "✓",
                    "missed" => "✗",
                    _ => "·",
                };
                println!("[points] {mark} [{}] {}", p.priority, p.text);
            }
        }
        EngineEvent::Wrap {
            summary,
            covered,
            missed,
        } => {
            println!(
                "[wrap] {}",
                if summary.is_empty() {
                    "(no summary)"
                } else {
                    summary
                }
            );
            println!("[wrap] covered {} · missed {}", covered.len(), missed.len());
            for m in missed {
                println!("[wrap] ✗ missed: {m}");
            }
        }
        EngineEvent::Error { message, fatal } => {
            println!("[error{}] {message}", if *fatal { "/fatal" } else { "" });
        }
        EngineEvent::Ended => println!("[ended]"),
    }
}

/// Plain stdin prompt (input is echoed — prefer $AMMEET_PASSWORD or --token).
fn prompt_password() -> Result<String, std::io::Error> {
    eprint!("password: ");
    std::io::stderr().flush()?;
    let mut line = String::new();
    std::io::stdin().read_line(&mut line)?;
    Ok(line.trim_end_matches(['\r', '\n']).to_string())
}
