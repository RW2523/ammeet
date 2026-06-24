# Running AmMeeting in bot-join mode (the bot attends the meeting)

This is the mode where AmMeeting **sends a bot into the meeting** to listen (recorder)
or speak as you (assistant) — as opposed to the bot-free notetaker (Chrome extension).

```
Backend (BOT_PROVIDER=browser)  →  bot-worker HTTP API (:4500)  →  Playwright Chromium  →  the meeting
        assistant/start                POST /bots                    joins, captions, audio
```

## 1. Start the bot-worker

```bash
cd bot-worker
npm install
PORT=4500 AUDIO_CAPTURE=on HEADLESS=true node src/server.js
# health: curl localhost:4500/health  →  {"status":"ok","bots":0}
```

## 2. Run the backend in bot-join mode

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://ammeet:ammeet_secret@localhost:5432/ammeet \
       REDIS_URL=redis://localhost:6379/0 \
       SECRET_KEY=ammeet-local-dev-secret-key-please-change-0123456789abcdef \
       BOT_PROVIDER=browser \
       BROWSER_BOT_WORKER_URL=http://localhost:4500
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## 3. Send the bot to a meeting (through the app)

```
POST /api/workspaces/{ws}/meetings/{id}/assistant/start
{ "mode": "recorder",   // "recorder" = listen silently;  "assistant" = listen + speak as you
  "simulate": false,    // false = deploy a REAL browser bot (true = scripted demo)
  "meeting_url": "https://meet.ffmuc.net/YourRoom" }
```
Poll `…/bot/status`, stream live events on `ws://…/api/ws/meetings/{id}`, stop with
`…/assistant/stop`.

## ✅ What is proven to work right now (no account needed)

Tested live, end-to-end through the running app on **Jitsi** (`meet.ffmuc.net`):
- `assistant/start {mode:recorder, simulate:false}` deploys a real Chromium bot.
- The bot **joins the meeting and stays in it** (`status: joining → in_meeting`, stable 30s+).
- The transcript pipeline polls Jitsi captions (empty only when nobody is speaking).
- `assistant/stop` cleanly removes the bot (worker bot count drops, no stray Chromium).

Any **open meeting** (Jitsi, or Zoom/Teams links that allow guests) works the same way.

## ⚠️ Google Meet — requires a one-time sign-in (Google blocks anonymous bots)

Google refuses any bot that isn't signed into a Google account (verified: *"You can't join
this video call — No one can join a meeting unless invited or admitted by the host"*). You
**cannot** automate the Google login (Google blocks that too). So sign the bot in **once**,
by hand, into a persistent profile the bot then reuses:

```bash
cd bot-worker
BOT_PROFILE_DIR=./profile npm run google-login
#  → a real Chrome window opens. Log in with a THROWAWAY Google account.
#  → solve any 2FA. Then press Ctrl+C. The session is saved to ./profile.
```

Now start the worker with that profile and the bot joins Meet already signed in:

```bash
PORT=4500 AUDIO_CAPTURE=on HEADLESS=true BOT_PROFILE_DIR=./profile node src/server.js
```

The bot will reach the Meet pre-join screen as a signed-in user and click **Ask to join** /
**Join now**. For a meeting it wasn't invited to, the **host still has to click "Admit"** —
that's Google's rule for every guest, bot or human.

## 🔊 Speaking (assistant mode talking out loud)

Listening works on the host. **Speaking into the meeting needs a virtual microphone**
(PulseAudio `virtmic`), which only exists in the Docker image:

```bash
docker build -t ammeet-bot-worker .
docker run -p 4500:4500 -e AUDIO_CAPTURE=on ammeet-bot-worker
```
The backend's `output_audio` → worker `POST /bots/:id/output-audio` plays TTS into `virtmic`,
so other participants hear the assistant. (On the bare host there is no virtual mic, so
speaking is a no-op there — join + listen still work.)
