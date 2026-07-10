# AmMeeting — Chrome Web Store listing

Package: `npm run pack` → produces `ammeet-extension.zip` (upload this at
https://chrome.google.com/webstore/devconsole).

## Name
AmMeeting — AI meeting co-pilot & speaking companion

## Short description (≤132 chars)
Silently ticks off your talking points as you speak, takes notes, and captures every answer — in Google Meet, Zoom & Teams.

## Category
Productivity

## Detailed description
AmMeeting is a silent AI co-pilot that helps you cover every point and leave every
meeting with organized outcomes — no bot joins your call, nothing to announce.

🎤 SPEAK MODE — never miss a point
Load your agenda, sermon outline, pitch, or interview questions. AmMeeting turns them
into a prioritized checklist and quietly ticks off each point the moment you say it.
Missed must-haves stay highlighted so you always know what's left — perfect for meetings,
client presentations, sermons, interviews, and product demos.

📝 NOTETAKER — bot-free
Captures the meeting's live captions from your own tab (no bot, no sign-in, no host
admission) and turns them into clean notes: summary, action items, decisions, risks.

🎧 CAPTURES EVERY ANSWER
Tracks participants' responses, questions, and decisions and links them to your points,
so nothing said gets lost.

📄 ORGANIZED OUTCOMES
Every session ends with a summary — covered points, missed points, audience responses,
action items, and follow-ups.

Private by design: works from your own browser tab. You choose when it listens.

## Permission justifications (for reviewers)
- **tabCapture** — optionally transcribe the other participants' audio from the active
  meeting tab, when the user explicitly enables it.
- **activeTab / scripting / tabs** — detect the active meeting tab (Meet/Zoom/Teams) and
  read its on-screen captions to build the transcript.
- **sidePanel** — the app's UI (checklist, notes) runs in Chrome's side panel.
- **storage** — remember the signed-in session and backend URL locally.
- **notifications** — alert the user to escalations / status changes.
- **alarms** — keep the background service worker responsive during a live session.
- **host_permissions (meet.google.com, zoom.us, teams.microsoft.com)** — required to read
  captions from the supported meeting platforms.

## Privacy
Audio is not stored. Caption text and (optionally) transcribed audio are sent only to the
user's configured AmMeeting backend to produce notes and track speaking points. The user
controls when capture is active.

## Screenshots to attach (1280×800)
1. Speak tab — live checklist with points ticking off + a highlighted missed must-have.
2. Notetaker tab — live transcript + generated notes.
3. Session summary — covered / missed / action items.
4. The side panel open next to a Google Meet.
