"""A stand-in for AnkiConnect, so that import can be tested without Anki.

It answers the handful of actions the tool uses and keeps every request it was
sent, which is what the import tests assert on: the note type's fields and their
order, the media uploaded before the note, and the note itself. Tests hold it to
whatever collection they need -- a deck that is absent, a note type that already
exists, an action it should refuse.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class StubAnki:
    """An AnkiConnect that answers from what a test configured, and remembers."""

    def __init__(
        self,
        *,
        deck_names: tuple[str, ...] = ("EnglishPod", "Default"),
        model_names: tuple[str, ...] = (),
        note_type: dict[str, Any] | None = None,
    ) -> None:
        self.deck_names = list(deck_names)
        self.model_names = list(model_names)
        # What the collection's note type holds, as `{"fields": [...],
        # "templates": {"Cloze": {"Front": ..., "Back": ...}}}`. A test that
        # makes the tool look at a note type already there sets this.
        self.note_type = note_type
        self.requests: list[dict[str, Any]] = []
        self.refusals: dict[str, str] = {}
        self.note_id = 1788443524727
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def sent(self, action: str) -> list[dict[str, Any]]:
        """Every request the tool sent for one action, in the order it sent them."""
        return [request["params"] for request in self.requests if request["action"] == action]

    def actions(self) -> list[str]:
        return [request["action"] for request in self.requests]

    def refuse(self, action: str, message: str) -> None:
        """Make one action answer the way a real AnkiConnect answers a refusal."""
        self.refusals[action] = message

    def answer(self, action: str, params: dict[str, Any]) -> Any:
        """The result of one action, as the collection it stands for would give it."""
        if action == "version":
            return 6
        if action == "deckNames":
            return self.deck_names
        if action == "modelNames":
            return self.model_names
        if action == "modelFieldNames":
            return self._note_type()["fields"]
        if action == "modelTemplates":
            return self._note_type()["templates"]
        if action == "createModel":
            self.model_names.append(params["modelName"])
            return {"id": 1761206860731, "name": params["modelName"]}
        if action == "storeMediaFile":
            return params["filename"]
        if action == "addNote":
            return self.note_id
        raise ValueError(f"the stub does not answer {action!r}")

    def _note_type(self) -> dict[str, Any]:
        if self.note_type is None:
            raise ValueError("this test's stub holds no note type to describe")
        return self.note_type


def _handler(stub: StubAnki) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 -- the name http.server calls
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            stub.requests.append(body)
            action = body["action"]
            if action in stub.refusals:
                reply = {"result": None, "error": stub.refusals[action]}
            else:
                reply = {"result": stub.answer(action, body.get("params") or {}), "error": None}
            encoded = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            """Keep the test output to the assertions."""

    return Handler
