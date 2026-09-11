"""A stand-in for the OCR service, so the pass can be tested without a key.

It answers the two calls the pass makes -- a key and a secret for a token, and a
page for the words on it -- and keeps every request it was sent, which is what
the tests assert on: that a page went up, that an ordinary run sent nothing, and
that the token was asked for once.

What it answers with is what a test lays out: lines of text with the coordinates
they would have been printed at. A line answers with the positions of its words,
the way the service does when it is asked to position every character and group
English into words, so the pass reads a page's layout out of it exactly as it
reads one out of a text layer.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs

# What one printed character takes up, in the coordinates a page is measured in:
# enough to lay a line out with, and nothing a page's geometry depends on.
CHARACTER = 7.0
LINE_HEIGHT = 12.0

TOKEN = "/oauth/2.0/token"
READ = "/rest/2.0/ocr/v1/accurate"

# Where the stub listens: the loopback address, as the service would be reached.
LOOPBACK = "127.0.0.1"


class StubOcr:
    """An OCR service that reads back whatever a test says the page says."""

    def __init__(self, lines: Sequence[tuple[str, float, float]] = ()) -> None:
        # Each line is its text, the left edge it starts at, and its top.
        self.lines = list(lines)
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.token = "stub-token"
        # What to refuse with, when a test wants the service to say no:
        # `{"error_code": 110, "error_msg": "Access token invalid"}`.
        self.refusal: dict[str, Any] | None = None
        self._server = ThreadingHTTPServer((LOOPBACK, 0), _handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK}:{self._server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def refuse(self, message: str, code: int = 110) -> None:
        """Make the service answer the way it does when it will not read a page."""
        self.refusal = {"error_code": code, "error_msg": message}

    def asked_for(self, path: str) -> list[dict[str, Any]]:
        """Every request the tool sent to one of the service's endpoints."""
        return [body for asked, body in self.requests if asked == path]

    def answer(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if self.refusal is not None:
            return self.refusal
        if path == TOKEN:
            return {"access_token": self.token, "expires_in": 2592000}
        if body.get("access_token") != self.token:
            # A page posted without the token it was issued is not one the tool
            # meant to send, and the service would say so.
            return {"error_code": 110, "error_msg": "Access token invalid or no longer valid"}
        return {"words_result_num": len(self.lines), "words_result": self._result()}

    def _result(self) -> list[dict[str, Any]]:
        """The page, as the service lays its answer out."""
        lines: list[dict[str, Any]] = []
        for text, left, top in self.lines:
            placed: list[dict[str, Any]] = []
            edge = left
            for word in text.split():
                placed.append(
                    {
                        "char": word,
                        "location": {
                            "left": edge,
                            "top": top,
                            "width": len(word) * CHARACTER,
                            "height": LINE_HEIGHT,
                        },
                    }
                )
                edge += (len(word) + 1) * CHARACTER
            lines.append(
                {
                    "words": text,
                    "location": {
                        "left": left,
                        "top": top,
                        "width": edge - left,
                        "height": LINE_HEIGHT,
                    },
                    "chars": placed,
                }
            )
        return lines


def _handler(stub: StubOcr) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 -- the name http.server calls
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            asked = self.path.partition("?")[0]
            sent = {name: values[0] for name, values in parse_qs(body).items()}
            stub.requests.append((asked, sent))
            reply = stub.answer(asked, sent)
            encoded = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            """Keep the test output to the assertions."""

    return Handler
