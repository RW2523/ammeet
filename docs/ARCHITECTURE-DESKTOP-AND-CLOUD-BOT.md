# AmMeeting — Phase 2 (Desktop App) & Phase 3 (Cloud Bot) Architecture

> **Status:** planning document — nothing in here is built yet except where marked `✅ exists`.
> **Prerequisite:** Phase 1 (extension + web hub) is shipped and should have real users
> before either phase starts. This doc exists so the build can start on evidence, not memory.

The governing model (see the vision page): **one brain, many bodies, one dial.**

```
BODIES (capture)              THE BRAIN (✅ exists, unchanged)        OUTPUTS
─────────────────             ────────────────────────────────       ─────────────────
Chrome extension  ✅  ──▶     FastAPI backend                  ──▶   Speak checklist
Desktop app   (Phase 2) ─▶      transcript pipeline            ──▶   Notes & summaries
Cloud bot     (Phase 3) ─▶      speak_coverage engine          ──▶   Shareable recaps /r/…
                                proxy_engine + escalation      ──▶   Slack / Jira drafts
                                knowledge base (pgvector)      ──▶   Searchable memory
                                LLM layer (hosted/BYOK/local)
```

**Design law for both phases:** a new body may NOT add intelligence. It only adds
capture and presentation. All reasoning stays in the backend so every body improves
at once. The extension proved this: Speak Mode shipped with zero backend changes
for the new surface.

---

# Part 1 — Phase 2: Desktop App

## 1.1 Product goals

| Goal | Why |
|---|---|
| Capture **any** meeting — native Zoom/Teams apps, Webex, Slack huddles, in-person | The extension only sees Meet/Zoom/Teams **web tabs**; most users run native apps |
| **No captions required** | Kills the #1 fragility of the caption path |
| **Local/private mode** — on-device STT + optional local LLM | The story no VC-funded competitor tells: "your audio never leaves the machine" |
| **Floating Speak overlay** — checklist over any app | The Speak Mode moat, freed from the browser side panel |
| **Voice-on-approval** (dial level 3) | AI drafts → user taps approve → spoken via virtual mic |

**Non-goals for Phase 2:** attending when absent (that's Phase 3), autonomous voice
(gated behind Phase 3 trust review), mobile.

## 1.2 Stack decision

| Layer | Choice | Rationale |
|---|---|---|
| Shell | **Tauri 2.x** (Rust core + webview UI) | ~10 MB binary vs ~150 MB Electron; direct native API access from Rust; low RAM for an always-on tray app |
| UI | **React + TypeScript + Tailwind** | Reuse Phase 1 component idioms (SidePanel, Speak pages) nearly verbatim |
| STT | **whisper.cpp** (bundled, Metal/AVX) | Proven on-device, fast on Apple Silicon; streaming via chunked decode |
| VAD | **Silero VAD** (ONNX, tiny) | Gate STT so we only transcribe speech, not silence |
| Local LLM (optional) | **Ollama** (detected if installed, never bundled) | "Fully local" tier without shipping a 4 GB model |
| Audio I/O | **cpal** + per-OS capture (below) | Rust-native, cross-platform mic handling |
| Packaging | Tauri bundler + updater | Signed DMG/MSI with auto-update channel |

**OS order: macOS first, Windows second, Linux later.**
macOS has the cleanest sanctioned system-audio API (ScreenCaptureKit), the
meeting-tools early-adopter market skews Mac (Granola launched Mac-only), and it
enables daily dogfooding. Windows follows once the Mac app is validated.

## 1.3 Process architecture

```
┌────────────────────────── Desktop app (one Tauri process) ──────────────────────────┐
│                                                                                     │
│  ┌─────────────┐   ┌──────────────────────────── Rust core ───────────────────────┐ │
│  │  Tray/menu  │   │                                                              │ │
│  │  bar icon   │   │  capture::system   ScreenCaptureKit / WASAPI loopback        │ │
│  └─────────────┘   │  capture::mic      cpal (user's real microphone)             │ │
│                    │  meeting_detect    audio-activity + calendar + focused app   │ │
│  ┌─────────────┐   │  vad               Silero — speech gating per stream         │ │
│  │  Main window│   │  stt               whisper.cpp — 2 independent decoders      │ │
│  │  (webview)  │◀──│  events            typed channel → UI (transcript lines)     │ │
│  └─────────────┘   │  sync              batched POST → backend /ingest, /speak    │ │
│                    │  voice (level 3)   TTS out → virtual-mic mixer               │ │
│  ┌─────────────┐   │  store             local SQLite (offline queue + settings)   │ │
│  │Speak overlay│   └──────────────────────────────────────────────────────────────┘ │
│  │(always-on-  │                                                                    │
│  │ top window) │        HTTPS (same JWT auth as extension)                          │
│  └─────────────┘                    │                                               │
└─────────────────────────────────────┼───────────────────────────────────────────────┘
                                      ▼
                        ✅ existing FastAPI backend (the brain)
```

## 1.4 Audio capture — the core capability

Two **physically separate** streams, preserving Phase 1's source-based
you-vs-them separation (no voice fingerprinting needed):

| Stream | Source | API | Tagged as |
|---|---|---|---|
| Them | System audio output (what the speakers play) | macOS: **ScreenCaptureKit** audio tap · Win: **WASAPI loopback** · Linux: **PipeWire** monitor | `Participants` |
| You | Real microphone | **cpal** | `You` |

Pipeline per stream (identical, independent):

```
raw PCM (48 kHz) → resample 16 kHz mono → Silero VAD (only speech passes)
  → whisper.cpp streaming decode (2–5 s segments, local)
  → {speaker: "You"|"Participants", text, ts}
  → UI event + batched POST /api/workspaces/…/speak/ingest  (existing endpoint)
```

Notes:
- Echo handling: the system stream contains only remote voices (platforms don't
  loop your own mic back), so the split is correct by construction — same
  property the extension relies on.
- Speaker diarization of the "them" bucket (pyannote) is **explicitly deferred**
  to Phase 2.5 — it's compute-heavy and the caption path already gives named
  speakers when available. Ship without it.
- Permissions required on macOS: Screen Recording (for SCK audio) + Microphone.
  First-run flow must explain both *before* triggering the prompts.

## 1.5 Meeting detection (auto-awareness)

The tray app knows a meeting is probably happening from three cheap signals:

1. **Calendar** — existing Google Calendar sync says an event is now (`✅ exists` in backend).
2. **App/window focus** — frontmost app is Zoom/Teams/Meet-in-browser/Webex.
3. **Audio activity** — sustained bidirectional audio (system out + mic in simultaneously).

Any two signals → notification: *"Looks like a meeting — start capturing?"*
(One-click start; **never auto-record without consent.** Auto-start is an explicit
opt-in setting, off by default.)

## 1.6 The Speak overlay

A separate always-on-top, frameless, translucent Tauri window (~320 px wide):

- Renders the same checklist state the extension side panel shows (same
  `/speak/state` polling + local push from the ingest response).
- Click-through except on interactive elements; draggable; collapses to a pill
  showing `6/9 · 1 must left`.
- Global hotkey (default `⌥⌘S`) toggles it.
- This is the demo moment: presenter shares their screen in Zoom while the
  overlay privately shows their ticking checklist.

## 1.7 Local / privacy mode

Three data postures, chosen per workspace in settings:

| Mode | STT | LLM | What leaves the machine |
|---|---|---|---|
| Cloud (default) | local whisper.cpp | hosted/BYOK via backend | transcript text |
| Hybrid | local | BYOK via backend | transcript text |
| **Fully local** | local | **Ollama** on-device | **nothing** — notes/points computed locally |

Fully-local mode requires a local execution path for `speak_coverage`-style
prompts. Implementation: the desktop app calls Ollama's OpenAI-compatible API
with the **same prompts** used by the backend (extract them into a shared
`prompts.json` in the repo so backend and desktop cannot drift). Results stay in
local SQLite; nothing syncs unless the user flips the mode.

## 1.8 Voice-on-approval (dial level 3)

Ladder, strictly in this order:

1. **Whisper-to-me (ship first):** suggested answers/points render in the overlay
   (optionally private TTS to headphones). No drivers, no disclosure needed —
   the human speaks. 80 % of the value, 5 % of the risk.
2. **Speak-on-approval (ship second):** requires a **virtual audio device**
   (macOS: audio server plugin / BlackHole-style; Win: bundled VB-Cable-style
   driver). A Rust mixer combines `real mic + TTS output → virtual mic`; the
   user selects "AmMeeting Mic" in Zoom once. AI drafts a reply → approval chip
   in the overlay → TTS plays into the mix. Auto-duck: any real-mic speech
   instantly mutes the TTS.
3. **Autonomous voice: NOT in Phase 2.** Inherits Phase 3's trust framework.

The driver install is the scariest step in the product — it gets its own
consent screen, is strictly optional, and levels 1–2 of the dial must work
without it.

## 1.9 Auth & sync

- Login via **device-code flow** against existing auth (`POST /api/auth/…` `✅ exists`):
  app shows a short code, user confirms in the web hub, app receives JWT pair.
  Refresh handled like the extension.
- Offline queue: transcript segments buffer in SQLite when the backend is
  unreachable; flush on reconnect (idempotent by `(meeting_id, ts, hash)`).

## 1.10 Packaging & release

- macOS: signed + **notarized** DMG; Sparkle-style updates via Tauri updater;
  Developer ID cert required (Apple Developer Program, $99/yr).
- Windows: signed MSI (EV cert or Azure Trusted Signing), same updater channel.
- CI: GitHub Actions matrix build (macos-14 arm64 + x86_64, windows-latest),
  release artifacts attached to tagged releases.

## 1.11 Milestones

| # | Milestone | Contents | Acceptance test |
|---|---|---|---|
| D1 | Skeleton + auth | Tauri app, tray icon, device-code login, settings | Logs in, shows workspaces from real backend |
| D2 | Capture core (macOS) | SCK system-audio + cpal mic → VAD → whisper.cpp → live transcript in window | Native-Zoom call transcribed with correct You/Participants tags, captions OFF |
| D3 | Brain hookup | Batched `/speak/ingest` + `/notes`; Speak tab parity with extension | Full Speak session (prepare→live→finalize→share) driven from desktop |
| D4 | Overlay | Always-on-top checklist, hotkey, pill mode | Points tick live over a full-screen Zoom share |
| D5 | Local mode | Ollama detection, shared prompts, local SQLite notes | Airplane-mode meeting produces points + summary, zero network calls |
| D6 | Ship | Signing, notarization, updater, crash reporting, Windows port begins | Fresh Mac: install → first meeting captured in < 5 min |
| D7 (2.5) | Voice ladder | Whisper-to-me, then virtual-mic speak-on-approval | Approved draft heard by remote participant; real-mic speech ducks it |

## 1.12 Risks

| Risk | Mitigation |
|---|---|
| macOS permission friction (Screen Recording prompt scares users) | Pre-permission explainer screens; capture works degraded (mic-only) if denied |
| whisper.cpp too slow on old Intel Macs | Model-size auto-select (tiny/base/small); cloud-STT fallback flag |
| Virtual-mic driver rejection/AV flags on Windows | Driver strictly optional; levels 1–2 never require it |
| Scope creep toward diarization/screen-OCR | Explicitly parked in Phase 2.5 backlog |

---

# Part 2 — Phase 3: Cloud Bot ("attend when I'm absent")

## 2.1 Product goals & staging

The delegate ships as three **separately gated stages** — outward risk rises at
each step, so trust must be earned at each step:

| Stage | Behavior | Speaks? | Risk |
|---|---|---|---|
| **A — Silent Delegate** | Joins, announces itself once, records, transcribes, files the same recap | Intro only | Low — ship first |
| **B — Briefed Delegate** | Delivers the user's **scripted** statements (reuses Speak points!), captures questions directed at the user into a follow-up list | Script only | Medium |
| **C — Interactive Delegate** | Answers live from the KB via `proxy_engine`, escalation-gated, with a real-time phone-approval channel | Generated, gated | High — last, legal-reviewed |

## 2.2 Provider strategy: buy the join, own the brain

```
                    MeetingBotProvider (✅ exists — base.py)
                    create_bot / status / transcript / speak / leave
                          ┌──────────────┴──────────────┐
              RecallProvider (✅ exists)        BrowserBotProvider (✅ exists)
              PRIMARY — production              SANDBOX — dev/demo + self-hosted Jitsi
              Meet/Zoom/Teams via Recall.ai     own infra; Meet blocks unsigned bots
```

- **Recall.ai is the production join layer.** It absorbs the per-platform
  restriction maze (Zoom SDK policy, Teams' Azure-only media bots, Meet's
  receive-only Media API and bot blocking). `recall.py` is already wired —
  production needs a funded API key + webhook URL config.
- **bot-worker stays** as the free dev sandbox (Jitsi E2E tests run against it,
  `✅ exists`) and a possible future self-hosted margin play. It is *not* the
  launch path for Meet/Zoom/Teams.
- The provider abstraction means switching is `BOT_PROVIDER=` config, not code.

## 2.3 Runtime architecture

```
Calendar sync (✅) ──▶ auto-join scheduler (✅ worker exists)
                            │  at scheduled_at, if delegate enabled + consent recorded
                            ▼
                    POST provider.create_bot(meeting_url, "«User»'s AI delegate")
                            │
        Recall webhook ──▶ /api/… transcript ingestion (✅ token-authed)
                            │
                            ▼
              ┌──────────── delegate session loop (NEW: delegate_engine.py) ───────────┐
              │ stage A: pipe segments → notetaker pipeline → recap                    │
              │ stage B: + script queue → provider.speak(next approved statement)      │
              │          + "questions for the user" detector → follow-up list         │
              │ stage C: + proxy_engine.answer() → escalation.check() →               │
              │            IF restricted → push notification → wait/approve/decline    │
              │            IF allowed   → provider.speak(answer)                      │
              └──────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
              same wrap as every body: report → recap link → knowledge base
```

New backend components (everything else `✅ exists`):

| Component | Purpose |
|---|---|
| `delegate_engine.py` | The session state machine above (stage A/B/C behaviors) |
| `DelegateSession` model + migration | stage, consent record, script items, follow-ups, audit pointer |
| Approval channel | WebSocket to web/desktop + push notification (email/SMS fallback); 30 s timeout → default **decline** |
| `delegate_sessions` billing metric | Paid-plan gate (this body costs real per-minute money) |

## 2.4 Trust & legal layer (non-negotiable, built WITH stage A)

1. **Disclosure on entry** — first utterance, hard-coded, not LLM-generated:
   *"Hi, I'm ‹name›'s AI delegate. ‹name› can't attend; I'll record and share a
   recap. I can't make commitments on their behalf."* Logged with timestamp.
2. **Consent** — meeting owner must enable delegate per-meeting
   (`proxy_consent_given ✅ exists`); host-admission counts as room consent;
   jurisdictions configurable to require explicit verbal acknowledgment.
3. **Never-commit invariant** — `escalation.py` (✅ fail-closed) intercepts
   budget/legal/HR/contract/deadline topics. Default utterance:
   *"I'll have to check with ‹name› on that — noted for follow-up."*
4. **Full audit** — every utterance the bot makes is stored verbatim
   (`AuditLog ✅ exists`) and shown in a "what your delegate said" section of the recap.
5. **Kill switch** — user (web/desktop/phone) can eject the bot instantly;
   any participant saying "drop the bot" is detected and honored.

## 2.5 Milestones

| # | Milestone | Contents | Acceptance test |
|---|---|---|---|
| B1 | Recall production wiring | Funded key, webhook config, status UI in web hub | Bot joins a real Meet, transcript flows, recap generated |
| B2 | Stage A end-to-end | Disclosure, auto-join from calendar, recap + share link, billing gate | Absent-user meeting produces recap indistinguishable from extension quality |
| B3 | Trust layer | Consent flow, audit surface in recap, kill switch | Kill switch removes bot < 5 s; audit shows every utterance |
| B4 | Stage B | Script queue from Speak points, question-capture list | Bot delivers 3 scripted updates; questions to the user land in follow-ups |
| B5 | Stage C (gated) | proxy answers + phone-approval loop, legal review complete | Restricted question → phone ping → approve → spoken; no approval → declined |

## 2.6 Risks

| Risk | Mitigation |
|---|---|
| Recall cost per minute at scale | Paid-plan only; per-workspace monthly caps; bot-worker/Jitsi as long-term self-host lever |
| Latency makes stage C feel broken | Stage C is opt-in and explicitly framed as "delegate, not conversationalist"; pre-approved answer bank for known topics |
| Legal exposure (recording consent, AI speech) | Stage-gated rollout; disclosure hard-coded; jurisdiction config; legal review is a B5 exit criterion |
| Host declines bot admission | Graceful: user notified immediately + prep material auto-shared with organizer |

---

# Part 3 — Shared foundations & sequencing

## 3.1 What both phases reuse unchanged

- Auth/JWT, workspaces, billing (`check_and_increment_usage`), LLM layer,
  `speak_coverage`, `proxy_engine`, `escalation`, notetaker pipeline,
  reports + share links (`/r/{token}`), knowledge base, audit log.
- **Rule:** if a phase needs new intelligence, it lands in the backend first,
  behind the same APIs, so the extension gains it too.

## 3.2 Sequencing (the honest order)

```
NOW          Ship Phase 1 to real users (Web Store listing, deploy backend+web)
   │         └─ gather: which dial levels do people actually use?
   ▼
GATE 1       ≥ ~50 active users / clear Speak-mode retention  ──▶ start Phase 2 (D1)
   ▼
Phase 2      D1→D6 macOS desktop; D7 voice ladder
   ▼
GATE 2       Desktop validates "power user" demand + revenue  ──▶ start Phase 3 (B1)
   ▼
Phase 3      B1→B3 silent delegate; B4 briefed; B5 interactive (legal-gated)
```

Both phases are architected here so each gate opens onto a plan, not a blank page —
but the gates are real: **do not start D1 with zero Phase 1 users.**
