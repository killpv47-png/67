"""Tiny fake Telegram Bot API HTTP server (stdlib only) for booting main.py as a real process.

Records every method call to a JSON-lines file and serves an empty getUpdates
with a short long-poll so the bot's poller behaves normally.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fake_tg.jsonl"
_mid = [100]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _reply(self, result):
        body = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        method = self.path.rsplit("/", 1)[-1]
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"_raw": raw[:200].decode(errors="replace")}
        with open(LOG, "a") as f:
            f.write(json.dumps({"method": method, "data": data}) + "\n")
        if method == "getMe":
            return self._reply({"id": 123456, "is_bot": True, "first_name": "ghbot", "username": "ghbot_test"})
        if method == "getUpdates":
            time.sleep(0.5)
            return self._reply([])
        if method in ("sendMessage", "editMessageText"):
            _mid[0] += 1
            return self._reply({"message_id": _mid[0], "date": int(time.time()), "chat": {"id": data.get("chat_id", 1), "type": "private"},
                                "text": data.get("text", "")})
        return self._reply(True)

    do_GET = do_POST


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("ready", flush=True)
    while True:
        time.sleep(1)
