from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


def _env(name: str) -> str:
    v = os.getenv(name, "")
    return v.strip()


EXPECTED_AUTH_HEADER = _env("WEBHOOK_AUTH_HEADER")  # e.g. "Authorization" or "X-Api-Key"
EXPECTED_TOKEN = _env("WEBHOOK_TOKEN")              # e.g. "Bearer abc" or "abc"


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self) -> None:  # noqa: N802
        # A tiny page so opening in browser doesn't spam 501.
        body = (
            "Webhook sink is running.\n\n"
            "POST alerts to /webhook\n"
            "Optional env:\n"
            "  WEBHOOK_AUTH_HEADER=Authorization\n"
            "  WEBHOOK_TOKEN=Bearer xxx\n"
        )
        self._send(200, body)

    def _check_auth(self) -> Optional[str]:
        # Returns error string if unauthorized, otherwise None.
        if not EXPECTED_AUTH_HEADER and not EXPECTED_TOKEN:
            return None

        if not EXPECTED_AUTH_HEADER:
            return "WEBHOOK_AUTH_HEADER not set but WEBHOOK_TOKEN is set"

        got = self.headers.get(EXPECTED_AUTH_HEADER)
        if got is None:
            return f"Missing auth header: {EXPECTED_AUTH_HEADER}"

        if EXPECTED_TOKEN and got.strip() != EXPECTED_TOKEN:
            return f"Invalid token in {EXPECTED_AUTH_HEADER},{got},{EXPECTED_TOKEN}"

        return None

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/webhook":
            return self._send(404, f"not found: {self.path}")

        err = self._check_auth()
        if err:
            print(f"[sink] unauthorized: {err}")
            return self._send(401, f"unauthorized: {err}")

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""

        print("\n====== WEBHOOK RECEIVED ======")
        print(f"path: {self.path}")
        print("headers:")
        for k, v in self.headers.items():
            print(f"  {k}: {v}")

        # Try JSON pretty print; fallback to raw text
        try:
            obj = json.loads(raw.decode("utf-8") if raw else "{}")
            print("body(json):")
            print(json.dumps(obj, ensure_ascii=False, indent=2))
        except Exception:
            print("body(raw):")
            print(raw.decode("utf-8", errors="replace"))

        self._send(200, "ok\n")

    def log_message(self, fmt: str, *args) -> None:
        # Keep it quiet; comment this out if you want standard access logs
        pass


def main() -> None:
    host = os.getenv("WEBHOOK_SINK_HOST", "127.0.0.1")
    port = int(os.getenv("WEBHOOK_SINK_PORT", "19099"))
    httpd = HTTPServer((host, port), _Handler)
    print(f"Webhook sink listening on http://{host}:{port}/webhook")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
