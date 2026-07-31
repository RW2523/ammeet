# AmMeeting desktop capture (minimal Phase-2 body)

A single-file capture client that proves the Phase-2 desktop architecture
end-to-end ahead of the full Tauri app: local STT on this machine, all
intelligence in the backend, live coverage + nudges presented in the
terminal (the "overlay pill", minus the overlay).

Per `docs/ARCHITECTURE-DESKTOP-AND-CLOUD-BOT.md`, the full desktop app
(Tauri, system-audio loopback, always-on-top overlay, voice ladder) is
gated on Phase-1 retention (GATE 1). This client is the D0 stopgap that
lets a laptop join the "many bodies" today.

## Install

```bash
cd desktop
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

`faster-whisper` (CPU int8) has wheels for x86_64 and arm64, macOS and
Linux. `--stdin` mode needs no dependencies at all — plain Python 3.10+.

## Use

Prepare a meeting with Speak points (web UI or extension), then:

```bash
# live microphone -> local Whisper -> Speak coverage
.venv/bin/python ammeet_capture.py --api https://spark-9f46.tail1917c3.ts.net:8443 \
  --email you@example.com --workspace-id WS --meeting-id MID --mic --finalize

# transcribe a recording after the fact
.venv/bin/python ammeet_capture.py --api ... --wav meeting.wav \
  --workspace-id WS --meeting-id MID --finalize

# no-STT smoke test: type/pipe "Speaker: text" lines
.venv/bin/python ammeet_capture.py --api ... --stdin \
  --workspace-id WS --meeting-id MID
```

Ctrl-C ends the session (`--finalize` prints the wrap summary, covered and
missed points).

## Honest limitations (why the Tauri app still matters)

- Mic only — everything is tagged "You". The participants stream needs
  OS-level system-audio capture (ScreenCaptureKit / WASAPI / PipeWire).
- Terminal output, not an always-on-top overlay; no hotkeys.
- Chunked STT (~5 s), no VAD-driven segmentation, no diarization.
