# AmMeeting Chrome Extension

AI meeting proxy assistant — represents you in Zoom, Google Meet, and Microsoft Teams using your browser's native STT/TTS plus the AmMeeting backend.

## 📝 Notetaker mode (bot-free) — the way real notetakers work

The big idea, borrowed from Otter / Fireflies / Fathom: **don't send a bot that has to
sign in and be admitted** (Google now blocks third-party notetaker bots by default).
Instead, capture the meeting from **your own browser tab** — you're already signed in and
admitted, so there's nothing to authenticate.

**How it works**
1. You join the Google Meet / Zoom / Teams call as normal and turn on **live captions (CC)**.
2. The content script (`caption-scraper.ts`) reads the caption lines from the page DOM.
3. The service worker batches them and `POST`s to the backend
   `…/notetaker/transcript`, which accumulates the transcript on the meeting.
4. The side panel's **📝 Notes** tab shows the live transcript and a **Generate notes**
   button → the backend LLM (your configured provider) returns summary, key points,
   action items, decisions, and risks.
5. **Stop & finalize** folds the transcript into the workspace knowledge base.

No bot joins, no Google sign-in, no host admission, no Recall.ai, no cost.

**Try it**
```bash
cd chrome-extension && npm install && npm run build
# Chrome → chrome://extensions → Developer mode → Load unpacked → select chrome-extension/dist
# In the side panel: set backend URL (http://localhost:8010), log in.
# Join a Google Meet, turn on captions (CC), pick a workspace+meeting in 🚀 Session,
# then open 📝 Notes → Start notetaker.
```

> **Note on verification:** the backend notetaker (transcript + AI notes) is fully built
> and live-tested (`/notetaker/*` endpoints, 4 passing tests, real notes generated via the
> configured LLM). The extension **builds and type-checks clean**. The one piece that needs
> a real meeting to validate is the **caption-DOM selectors** in `caption-scraper.ts` —
> Google/Zoom/Teams obfuscate and change these, so they may need tuning against a live
> meeting (the architecture is identical to how Fathom/tl;dv scrape captions).

## Architecture

```
chrome-extension/
├── manifest.json                    Manifest V3
├── src/
│   ├── background/
│   │   └── service-worker.ts        Auth, API relay, message broker, notifications
│   ├── content/
│   │   ├── meeting-detector.ts      Zoom/Meet/Teams DOM detection + participant scraping
│   │   └── injected-overlay.ts      Shadow-DOM status badge injected into meeting pages
│   ├── sidepanel/
│   │   ├── SidePanel.tsx            Main UI — session control, transcript, events, settings
│   │   ├── index.css                Tailwind + dark-mode styles
│   │   └── main.tsx                 React entry point
│   ├── popup/
│   │   ├── Popup.tsx                Toolbar popup — status, quick controls
│   │   └── main.tsx                 React entry point
│   └── lib/
│       ├── types.ts                 Shared TypeScript types + message protocol
│       ├── api.ts                   AmMeeting backend HTTP client
│       ├── stt.ts                   Web Speech API STT + tabCapture + MediaRecorder
│       ├── tts.ts                   speechSynthesis TTS + AudioContext MP3 playback
│       ├── websocket.ts             Reconnecting WebSocket manager
│       ├── store.ts                 chrome.storage.local typed helpers
│       └── speech.d.ts              SpeechRecognition type declarations
└── icons/
    ├── icon16.png  icon32.png  icon48.png  icon128.png
```

## Browser APIs Used (no backend needed)

| Feature | API |
|---------|-----|
| **STT live transcription** | `SpeechRecognition` / `webkitSpeechRecognition` |
| **Tab audio capture** | `chrome.tabCapture` |
| **Record mic audio** | `MediaRecorder` → upload to Whisper |
| **AI voice playback** | `speechSynthesis` (browser TTS) + `AudioContext` (MP3) |
| **Meeting detection** | DOM MutationObserver + URL matching |
| **State persistence** | `chrome.storage.local` |
| **Notifications** | `chrome.notifications` |
| **Side panel** | `chrome.sidePanel` |
| **Real-time events** | Native `WebSocket` (to AmMeeting backend) |

## Features Requiring Backend (AmMeeting FastAPI)

- LLM question generation (OpenAI / Anthropic)
- RAG knowledge base queries (pgvector)
- Whisper transcription (for uploaded audio files)
- OpenAI TTS (higher-quality MP3, sent as base64)
- Recall.ai meeting bot (physically joins Zoom/Meet/Teams)
- Escalation classification
- Report generation

## Setup

### 1. Build the extension

```bash
npm install
npm run build
# Outputs to dist/
```

### 2. Load in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `dist/` folder

### 3. Configure backend URL

1. Click the AmMeeting icon in the toolbar
2. Open the side panel
3. Go to **Settings** tab
4. Set **Backend URL** to your AmMeeting backend (default: `http://localhost:8000`)
5. Sign in with your AmMeeting account credentials

### 4. Using the extension

#### Simulation mode (no Zoom/Meet/Teams needed)
1. Select a workspace and meeting with proxy consent enabled
2. Check **Simulation mode**
3. Click **Start Session** — the AI generates answers and walks through questions

#### Live mode with a real meeting
1. Join your Zoom / Google Meet / Teams meeting in a browser tab
2. The extension detects the meeting and shows a green badge
3. In AmMeeting, ensure `BOT_PROVIDER=recall` and `RECALL_API_KEY` are set in `.env`
4. Select the matching meeting from the dropdown
5. Uncheck simulation mode, click **Start Session**
6. The Recall.ai bot joins the meeting, speaks questions aloud, and collects answers in real time

#### STT options
- **Start Mic STT** — uses browser Web Speech API to transcribe your microphone in real time (no backend required)
- **Record** — records mic audio, uploads to OpenAI Whisper on stop
- The live transcript tab shows all spoken text with speaker labels

#### TTS
- **TTS On** — plays AI utterances as audio using either:
  - OpenAI TTS MP3 (if backend has OPENAI_API_KEY set)
  - Browser `speechSynthesis` fallback (always available in Chrome)

## Building for production / Chrome Web Store

```bash
npm run pack
# Creates ammeet-extension.zip — upload to Chrome Web Store Developer Dashboard
```

## Environment

The extension talks to any AmMeeting backend. The backend URL is stored in `chrome.storage.local` and is user-configurable from the Settings tab.

For production, point the extension at your hosted backend URL (e.g. `https://api.yourdomain.com`), and update `host_permissions` in `manifest.json`.
