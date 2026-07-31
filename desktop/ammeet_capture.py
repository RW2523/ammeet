#!/usr/bin/env python3
"""AmMeeting desktop capture client — the minimal Phase-2 "body".

Captures speech on this machine, transcribes it locally (faster-whisper, CPU),
and streams it to the backend's Speak engine, printing live coverage and
nudges in the terminal. All intelligence stays in the backend ("one brain,
many bodies"); this client only captures and presents.

Sources:
  --stdin        read "Speaker: text" lines (no STT dependency needed)
  --wav FILE     transcribe an audio file locally, then ingest
  --mic          live microphone capture -> local STT -> ingest

Everything is tagged as the owner's speech ("You") except --stdin lines,
which carry their own speaker labels. System-audio ("Participants") capture
needs the OS virtual-device work scheduled for the real Tauri app.
"""
from __future__ import annotations

import argparse
import getpass
import json
import signal
import sys
import time
import urllib.error
import urllib.request

CHUNK_SECONDS = 5.0
INGEST_EVERY = 4.0
SAMPLE_RATE = 16000


class Api:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            raise SystemExit(f"API {e.code} on {path}: {detail}") from e


def login(base: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        base.rstrip("/") + "/api/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())["access_token"]


def print_state(state: dict) -> None:
    prog = state.get("progress", {})
    pill = (
        f"\r[{prog.get('covered', 0)}/{prog.get('total', 0)} covered"
        f" · {prog.get('must_remaining', 0)} must left]"
    )
    sys.stdout.write(pill.ljust(40))
    sys.stdout.flush()
    for pid in state.get("newly_covered", []):
        point = next((p for p in state.get("points", []) if p.get("id") == pid), None)
        if point:
            print(f"\n  ✓ covered: {point.get('text', '')[:70]}")
    for nudge in state.get("nudges", []) or []:
        label = {
            "promise": "YOU PROMISED",
            "unanswered": "STILL UNANSWERED",
            "conflict": "CONFLICTS WITH A DECISION",
        }.get(nudge.get("kind", ""), "NUDGE")
        print(f"\n  ⚡ {label}: {nudge.get('text', '')[:90]}")


class Ingestor:
    """Batches segments and ships them to /speak/ingest on a fixed cadence."""

    def __init__(self, api: Api, workspace_id: str, meeting_id: str) -> None:
        self.api = api
        self.path = f"/api/workspaces/{workspace_id}/meetings/{meeting_id}"
        self.pending: list[dict] = []
        self.seen_nudges: set[str] = set()
        self.last_send = 0.0

    def add(self, speaker: str, text: str) -> None:
        text = text.strip()
        if text:
            self.pending.append({"speaker": speaker, "text": text})

    def maybe_flush(self, force: bool = False) -> None:
        if not self.pending:
            return
        if not force and time.monotonic() - self.last_send < INGEST_EVERY:
            return
        segments, self.pending = self.pending, []
        self.last_send = time.monotonic()
        state = self.api.call("POST", self.path + "/speak/ingest", {"segments": segments})
        # A nudge repeats on later ticks while it stays relevant — show it once.
        fresh = []
        for n in state.get("nudges", []) or []:
            key = f"{n.get('kind')}|{n.get('item_id') or n.get('text')}"
            if key not in self.seen_nudges:
                self.seen_nudges.add(key)
                fresh.append(n)
        state["nudges"] = fresh
        print_state(state)

    def finalize(self) -> None:
        self.maybe_flush(force=True)
        report = self.api.call("POST", self.path + "/speak/finalize")
        print("\n\n── Session wrap " + "─" * 40)
        print(report.get("summary", "(no summary)"))
        covered, missed = report.get("covered", []), report.get("missed", [])
        print(f"covered {len(covered)} · missed {len(missed)}")
        for text in missed:
            print(f"  ✗ missed: {text[:70]}")


def transcribe_wav(path: str):
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path, vad_filter=True)
    for seg in segments:
        yield seg.text


def run_mic(ingestor: Ingestor) -> None:
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    print("mic capture started — Ctrl-C to finish")
    while True:
        audio = sd.rec(int(CHUNK_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                       channels=1, dtype="float32")
        sd.wait()
        segments, _info = model.transcribe(np.squeeze(audio), vad_filter=True)
        for seg in segments:
            ingestor.add("You", seg.text)
        ingestor.maybe_flush()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True, help="backend base URL")
    ap.add_argument("--email")
    ap.add_argument("--token", help="access token (skips login)")
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--meeting-id", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--stdin", action="store_true")
    src.add_argument("--wav")
    src.add_argument("--mic", action="store_true")
    ap.add_argument("--finalize", action="store_true",
                    help="finalize the Speak session when the source ends")
    args = ap.parse_args()

    token = args.token
    if not token:
        if not args.email:
            ap.error("--email (with password prompt) or --token is required")
        token = login(args.api, args.email, getpass.getpass("password: "))

    api = Api(args.api, token)
    ingestor = Ingestor(api, args.workspace_id, args.meeting_id)

    def finish(*_sig) -> None:
        if args.finalize:
            ingestor.finalize()
        else:
            ingestor.maybe_flush(force=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, finish)

    if args.stdin:
        print('reading "Speaker: text" lines from stdin — EOF/Ctrl-C to finish')
        for line in sys.stdin:
            speaker, _, text = line.partition(":")
            if text:
                ingestor.add(speaker.strip() or "You", text)
                ingestor.maybe_flush()
        finish()
    elif args.wav:
        for text in transcribe_wav(args.wav):
            ingestor.add("You", text)
        ingestor.maybe_flush(force=True)
        finish()
    else:
        run_mic(ingestor)


if __name__ == "__main__":
    main()
