import { useCallback, useEffect, useState } from "react";
import { api, isTauri, on } from "../ipc";
import { useEngineSync, useSession } from "../store";
import {
  DEFAULT_BASE_URL,
  MODEL_PROGRESS,
  type MeetingInfo,
  type ModelProgress,
  type Point,
  type SourceSpec,
  type WorkspaceInfo,
} from "../types";

const MODELS = ["tiny.en", "base.en", "small"] as const;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function Settings() {
  useEngineSync();

  // backend + auth
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loggedIn, setLoggedIn] = useState(false);

  // pickers
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [meetings, setMeetings] = useState<MeetingInfo[]>([]);
  const [meetingId, setMeetingId] = useState("");
  const [newTitle, setNewTitle] = useState("");

  // points
  const [notes, setNotes] = useState("");
  const [genPoints, setGenPoints] = useState<Point[]>([]);

  // source + model
  const [sourceType, setSourceType] = useState<"mic" | "wav">("mic");
  const [micDevice, setMicDevice] = useState("");
  const [wavPath, setWavPath] = useState("");
  const [model, setModel] = useState<string>("base.en");
  const [modelProgress, setModelProgress] = useState<ModelProgress | null>(null);

  // ux
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const phase = useSession((s) => s.phase);
  const covered = useSession((s) => s.covered);
  const total = useSession((s) => s.total);
  const engineError = useSession((s) => s.lastError);

  const loadWorkspaces = useCallback(async () => {
    try {
      const ws = await api.listWorkspaces();
      setWorkspaces(ws);
      if (ws.length === 1) setWorkspaceId(ws[0].id);
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  // Initial config + model-progress subscription.
  useEffect(() => {
    if (!isTauri) return;
    void (async () => {
      try {
        const cfg = await api.getConfig();
        setBaseUrl(cfg.base_url || DEFAULT_BASE_URL);
        setEmail(cfg.email);
        setModel(cfg.whisper_model || "base.en");
        if (cfg.logged_in) {
          setLoggedIn(true);
          void loadWorkspaces();
        }
      } catch (e) {
        setError(errText(e));
      }
    })();
    let unsub: (() => void) | null = null;
    let alive = true;
    void on<ModelProgress>(MODEL_PROGRESS, (p) => setModelProgress(p)).then(
      (u) => {
        if (alive) unsub = u;
        else u();
      },
    );
    return () => {
      alive = false;
      unsub?.();
    };
  }, [loadWorkspaces]);

  // Meetings follow the selected workspace.
  useEffect(() => {
    setMeetings([]);
    setMeetingId("");
    if (!workspaceId) return;
    void (async () => {
      try {
        setMeetings(await api.listMeetings(workspaceId));
      } catch (e) {
        setError(errText(e));
      }
    })();
  }, [workspaceId]);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const doLogin = () =>
    run("login", async () => {
      await api.login(baseUrl, email, password);
      setPassword("");
      setLoggedIn(true);
      await loadWorkspaces();
    });

  const doCreateMeeting = () =>
    run("create", async () => {
      const m = await api.createMeeting(workspaceId, newTitle);
      setNewTitle("");
      const ms = await api.listMeetings(workspaceId);
      setMeetings(ms);
      if (m && typeof m.id === "string") setMeetingId(m.id);
    });

  const doGenerate = () =>
    run("generate", async () => {
      setGenPoints(await api.generatePoints(workspaceId, meetingId, notes));
    });

  const doPrepareModel = () =>
    run("model", async () => {
      await api.pickModel(model);
    });

  const doStart = () =>
    run("start", async () => {
      const source: SourceSpec =
        sourceType === "mic"
          ? { type: "mic", device: micDevice.trim() ? micDevice.trim() : null }
          : { type: "wav", path: wavPath.trim() };
      await api.startSession({
        workspace_id: workspaceId,
        meeting_id: meetingId,
        source,
        model,
      });
    });

  const doStop = () => run("stop", () => api.stopSession().then(() => undefined));

  const sessionActive = phase === "running" || phase === "starting";
  const canStart =
    loggedIn &&
    !!workspaceId &&
    !!meetingId &&
    !sessionActive &&
    (sourceType === "mic" || wavPath.trim().length > 0);

  const statusLine = (() => {
    if (!isTauri) return "Browser preview — Tauri commands disabled";
    if (busy === "start" || phase === "starting") return "Session: starting…";
    if (phase === "running")
      return `Session: running — ${covered}/${total} covered`;
    if (phase === "wrapped") return "Session: finished — wrap ready in overlay";
    return loggedIn ? "Session: idle" : "Not logged in";
  })();

  return (
    <div className="settings">
      <header className="settings-head">
        <span className="logo">AM</span>
        <div>
          <h1>AmMeeting</h1>
          <p className="sub">Desktop capture · Speak overlay</p>
        </div>
      </header>

      {error && <div className="banner banner-error">{error}</div>}
      {engineError && !error && (
        <div className="banner banner-error">Engine: {engineError}</div>
      )}

      <section className="card">
        <h2>Backend &amp; account</h2>
        <label>
          Backend URL
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={DEFAULT_BASE_URL}
            spellCheck={false}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            spellCheck={false}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void doLogin();
            }}
          />
        </label>
        <div className="row">
          <button
            className="btn btn-primary"
            disabled={busy !== null || !email || !password}
            onClick={() => void doLogin()}
          >
            {busy === "login" ? "Logging in…" : loggedIn ? "Re-login" : "Log in"}
          </button>
          {loggedIn && <span className="ok-chip">✓ logged in</span>}
        </div>
      </section>

      <section className="card">
        <h2>Meeting</h2>
        <label>
          Workspace
          <select
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
            disabled={!loggedIn}
          >
            <option value="">— select workspace —</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Meeting
          <select
            value={meetingId}
            onChange={(e) => setMeetingId(e.target.value)}
            disabled={!workspaceId}
          >
            <option value="">— select meeting —</option>
            {meetings.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </select>
        </label>
        <div className="row">
          <input
            className="grow"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="New meeting title…"
            disabled={!workspaceId}
          />
          <button
            className="btn"
            disabled={busy !== null || !workspaceId || !newTitle.trim()}
            onClick={() => void doCreateMeeting()}
          >
            {busy === "create" ? "Creating…" : "Create"}
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Talking points</h2>
        <textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={
            "Paste prep notes — the backend turns them into a Speak checklist…"
          }
        />
        <div className="row">
          <button
            className="btn"
            disabled={busy !== null || !workspaceId || !meetingId || !notes.trim()}
            onClick={() => void doGenerate()}
          >
            {busy === "generate" ? "Generating…" : "Generate points"}
          </button>
          {genPoints.length > 0 && (
            <span className="muted">{genPoints.length} points</span>
          )}
        </div>
        {genPoints.length > 0 && (
          <ul className="gen-points">
            {genPoints.map((p) => (
              <li key={p.id} className={p.priority === "must" ? "must" : ""}>
                <span className="stage-tag">{p.stage}</span> {p.text}
                {p.priority === "must" && <b> · must</b>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Audio source</h2>
        <div className="row radio-row">
          <label className="radio">
            <input
              type="radio"
              checked={sourceType === "mic"}
              onChange={() => setSourceType("mic")}
            />
            Microphone
          </label>
          <label className="radio">
            <input
              type="radio"
              checked={sourceType === "wav"}
              onChange={() => setSourceType("wav")}
            />
            WAV file (testing)
          </label>
        </div>
        {sourceType === "mic" ? (
          <label>
            Device (optional, default input if empty)
            <input
              value={micDevice}
              onChange={(e) => setMicDevice(e.target.value)}
              placeholder="System default"
            />
          </label>
        ) : (
          <label>
            WAV path
            <input
              value={wavPath}
              onChange={(e) => setWavPath(e.target.value)}
              placeholder="/path/to/meeting.wav"
              spellCheck={false}
            />
          </label>
        )}
      </section>

      <section className="card">
        <h2>Whisper model</h2>
        <div className="row">
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {MODELS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            className="btn"
            disabled={busy !== null}
            onClick={() => void doPrepareModel()}
          >
            {busy === "model" ? "Preparing…" : "Prepare"}
          </button>
        </div>
        <p className="muted">
          Models download on first use.
          {modelProgress &&
            modelProgress.status === "preparing" &&
            ` Preparing ${modelProgress.name}…`}
          {modelProgress &&
            modelProgress.status === "ready" &&
            ` ${modelProgress.name} ready.`}
          {modelProgress &&
            modelProgress.status === "error" &&
            ` ${modelProgress.name} failed: ${modelProgress.message ?? "unknown error"}`}
        </p>
      </section>

      <section className="card">
        <h2>Session</h2>
        <div className="row">
          <button
            className="btn btn-primary"
            disabled={busy !== null || !canStart}
            onClick={() => void doStart()}
          >
            {busy === "start" ? "Starting…" : "Start session"}
          </button>
          <button
            className="btn btn-danger"
            disabled={busy !== null || !sessionActive}
            onClick={() => void doStop()}
          >
            {busy === "stop" ? "Stopping…" : "Stop"}
          </button>
        </div>
        <p className={`status-line ${sessionActive ? "live" : ""}`}>{statusLine}</p>
      </section>

      <footer className="settings-foot">
        <button className="link" onClick={() => void api.toggleOverlay()}>
          Toggle overlay (⌘⌥S / Ctrl+Alt+S)
        </button>
        <button className="link danger" onClick={() => void api.quit()}>
          Quit
        </button>
      </footer>
    </div>
  );
}
