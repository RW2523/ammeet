# AmMeeting Bot Worker (self-hosted meeting bot)

A headless-browser meeting bot that **actually joins** Zoom / Google Meet / Microsoft
Teams / Jitsi calls — a self-hosted, no-cost alternative to Recall.ai. It runs Chromium
via Playwright, joins the meeting, captures the conversation, can speak into the call,
and reports transcript back to AmMeeting using the **same webhook contract as Recall**,
so the existing proxy engine and meeting-assistant agent use it unchanged.

## How it plugs into AmMeeting

```
AmMeeting backend  ──create_bot──►  bot-worker (this service) ──Playwright──► real meeting
        ▲                                   │
        └────── transcript webhook ◄────────┘   POST /api/webhooks/recall/{meeting_id}
```

`BrowserBotProvider` (backend/app/services/meeting_bot/browser.py) implements the same
`MeetingBotProvider` interface as the Recall provider and calls this worker's HTTP API.
Because the worker and backend are co-located, **no public webhook / ngrok is needed**.

## HTTP API

| Method & path | Purpose |
|---|---|
| `POST /bots` `{meeting_url, display_name, webhook_url}` | Deploy a bot, join the meeting |
| `GET /bots/:id` | Status (`joining` / `in_meeting` / `done` / `error`) |
| `GET /bots/:id/transcript` | Captured segments |
| `POST /bots/:id/output-audio` `{b64}` | Speak (MP3 base64) into the meeting |
| `POST /bots/:id/leave` | Leave + tear down |
| `GET /health` | Liveness |

## Run it

```bash
# Build + run the container (Chromium + PulseAudio virtual audio baked in)
cd bot-worker
docker build -t ammeet-bot-worker:dev .
docker run -d -p 4500:4500 ammeet-bot-worker:dev

# …or via the main compose (profile-gated because it's heavy):
docker compose --profile bots up -d bot-worker
```

Then point AmMeeting at it (backend `.env`):

```
BOT_PROVIDER=browser
BROWSER_BOT_WORKER_URL=http://localhost:4500      # or http://bot-worker:4500 in compose
WEBHOOK_BASE_URL=http://localhost:8010            # your backend URL (the worker POSTs here)
```

Now start the Meeting Assistant / proxy on a meeting with a real `meeting_url` and
`simulate=false` — the self-hosted bot joins for real.

## Audio model (production)

The Docker image runs a PulseAudio virtual-audio stack (`docker/entrypoint.sh`):
- **vspeaker** — a null sink the browser plays meeting audio into; capture its monitor for STT.
- **virtmic** — a virtual microphone the browser uses; the worker plays TTS into
  `virtmic_sink` so other participants hear the assistant (`output_audio`).

## ✅ Verification status (honest)

**Verified working (tested in this build):**
- Headless browser **joins a real WebRTC meeting** — confirmed on `meet.ffmuc.net`
  (open Jitsi), both on the host and **inside the Docker container** (`status: in_meeting`,
  Jitsi `isJoined()=true`, participant count = 1, screenshot of the in-call UI).
- Worker HTTP API end-to-end; **transcript webhook** delivers events to AmMeeting in the
  Recall format (`bot.in_call_recording`, `transcript.final`, `bot.call_ended`).
- `BrowserBotProvider` ↔ worker contract (backend unit tests).
- Docker image **builds and boots** (PulseAudio virtual devices + worker).

**Implemented but needs your accounts / a live meeting to validate:**
- **Google Meet / Teams / Zoom** join flows (`src/platforms.js`): the click-paths are
  implemented, but these platforms require a **signed-in bot account** and usually
  **host admission**, so they need a real meeting + credentials to confirm end-to-end.
- **Live audio capture (speech→text) and speaking**: the virtual-audio plumbing is in the
  image, but validating real audio needs a meeting **with participants who actually speak**
  (an empty test room produces no audio/captions). To finish: route Chromium to the Pulse
  devices (drop `--use-fake-device-for-media-stream`), capture `vspeaker.monitor` → STT, and
  confirm `output_audio` is heard by a second participant.

## Notes / gotchas

- **Pin Playwright to the base image's version** (`mcr.microsoft.com/playwright:vX.Y.Z`
  must match `playwright` in package.json) — a mismatch makes `chromium.launch()` fail and
  the bot hangs at `joining`. Currently pinned to **1.49.1**.
- `meet.jit.si` now requires an authenticated moderator to *start* a room; use an open
  instance (e.g. `meet.ffmuc.net`) or self-host Jitsi for credential-free testing.
- One Chromium container handles one meeting; scale with one container per concurrent call.
- Respect recording-consent laws — AmMeeting already enforces a consent gate + spoken disclosure.
