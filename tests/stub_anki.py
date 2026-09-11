"""A stand-in for AnkiConnect, so that import can be tested without Anki.

It answers the handful of actions the tool uses and keeps every request it was
sent, which is what the import tests assert on: the note type's fields and their
order, the media uploaded before the note, and the note itself. Tests hold it to
whatever collection they need -- a deck that is absent, a note type that already
exists, notes the collection already holds, an action it should refuse.

A note already in the collection is held here as the collection holds it: its
identity, the note type and deck it belongs to, its fields, and the scheduling
of the card it makes. A test can read one back after a run to see what a replace
did to it -- which is how a replace is shown to keep the card's scheduling and
review history rather than making the card again.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Sequence

# The scheduling a card carries, for a note a test puts in the collection
# without saying otherwise: what a replace must leave exactly where it found it.
DEFAULT_SCHEDULING = {"due": 1791048000, "interval": 21, "reps": 34, "lapses": 2}


def existing(
    *,
    # Older than the id `addNote` answers with, so that a test can tell the note
    # a run refreshed from the one it made.
    note_id: int = 1603242736000,
    note_type: str = "EnglishPod Cloze",
    deck: str = "EnglishPod",
    tags: Sequence[str] = (),
    fields: Mapping[str, str] | None = None,
    scheduling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One note the collection already holds, as a test sets it up."""
    return {
        "noteId": note_id,
        "modelName": note_type,
        "deck": deck,
        "tags": list(tags),
        "fields": dict(fields or {}),
        "card": dict(scheduling or DEFAULT_SCHEDULING),
    }


class StubAnki:
    """An AnkiConnect that answers from what a test configured, and remembers."""

    def __init__(
        self,
        *,
        deck_names: tuple[str, ...] = ("EnglishPod", "Default"),
        model_names: tuple[str, ...] = (),
        note_types: Mapping[str, Mapping[str, Any]] | None = None,
        notes: Sequence[Mapping[str, Any]] = (),
        vanished: Sequence[int] = (),
    ) -> None:
        self.deck_names = list(deck_names)
        # What the collection's note types hold, by name, each as
        # `{"fields": [...], "templates": {"Cloze": {"Front": ..., "Back": ...}}}`.
        # A test that makes the tool look at a note type already there -- and
        # the learner's collection holds more than the one this tool makes --
        # sets this. Naming none is what a collection with the deck alone has.
        self.note_types: dict[str, dict[str, Any]] = {
            name: dict(design) for name, design in (note_types or {}).items()
        }
        self.model_names: list[str] = list(model_names) or list(self.note_types)
        # The notes the collection already holds, made with `existing()`.
        self.notes: list[dict[str, Any]] = [dict(note) for note in notes]
        # Ids a search finds that are gone by the time the run reads them: a
        # note deleted or synced away between the two, which is what the real
        # AnkiConnect answers an empty object for.
        self.vanished = list(vanished)
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

    def holds(self, note_id: int) -> bool:
        return any(note["noteId"] == note_id for note in self.notes)

    def note(self, note_id: int) -> dict[str, Any]:
        """One note the collection holds, as it stands now."""
        for held in self.notes:
            if held["noteId"] == note_id:
                return held
        raise ValueError(f"the collection holds no note {note_id}")

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
            return self._note_type(params["modelName"])["fields"]
        if action == "modelTemplates":
            return self._note_type(params["modelName"])["templates"]
        if action == "findNotes":
            in_deck = [note["noteId"] for note in self.notes if note["deck"] == _deck(params["query"])]
            return in_deck + self.vanished
        if action == "notesInfo":
            return [self._info(note_id) if self.holds(note_id) else {} for note_id in params["notes"]]
        if action == "updateNoteFields":
            self._update(params["note"])
            return None
        if action == "createModel":
            self.model_names.append(params["modelName"])
            # Anki then holds the note type it was asked to make, and answers
            # for it -- which a run over a corpus asks of the second note on.
            self.note_types[params["modelName"]] = {
                "fields": params["inOrderFields"],
                "templates": {
                    template["Name"]: {
                        "Front": template["Front"],
                        "Back": template["Back"],
                    }
                    for template in params["cardTemplates"]
                },
            }
            return {"id": 1761206860731, "name": params["modelName"]}
        if action == "storeMediaFile":
            return params["filename"]
        if action == "addNote":
            return self.note_id
        raise ValueError(f"the stub does not answer {action!r}")

    def _note_type(self, name: str) -> dict[str, Any]:
        if name not in self.note_types:
            raise ValueError(f"this test's stub holds no note type named {name!r}")
        return self.note_types[name]

    def _info(self, note_id: int) -> dict[str, Any]:
        """One note as AnkiConnect describes it, with its fields and their order."""
        note = self.note(note_id)
        return {
            "noteId": note["noteId"],
            "modelName": note["modelName"],
            "tags": note["tags"],
            "fields": {
                name: {"value": value, "order": order}
                for order, (name, value) in enumerate(note["fields"].items())
            },
        }

    def _update(self, note: Mapping[str, Any]) -> None:
        """Change the fields of a note already there, and nothing else.

        `updateNoteFields` touches fields alone: the card the note makes keeps
        its scheduling and its review history, which is the whole point of it.
        """
        self.note(note["id"])["fields"].update(note["fields"])


# The tool searches one deck at a time, and the stub knows no search language
# beyond naming it: a query of any other shape is one it cannot answer, and says
# so rather than answering the wrong question.
DECK = re.compile(r'deck:"([^"]*)"')


def _deck(query: str) -> str:
    if not (match := DECK.fullmatch(query.strip())):
        raise ValueError(f"the stub does not search for {query!r}")
    return match.group(1)


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
