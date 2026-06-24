"""Minimal webhook receiver — logs every POST the bot-worker sends (mimics AmMeeting's Recall webhook)."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode() if n else ""
        try:
            data = json.loads(body)
            print(f"WEBHOOK event={data.get('event')!r} data={data.get('data')}", flush=True)
        except Exception:
            print(f"WEBHOOK raw={body[:200]}", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", 4599), H).serve_forever()
