"""Talking to a running Anki through AnkiConnect.

AnkiConnect is one HTTP endpoint answering one JSON request per action. Only the
actions making a card needs are here, each answering a plain value or raising
`AnkiConnectError` with something a person can act on -- a collection the tool
cannot reach is a setup problem, not a stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen

# AnkiConnect listens here by default, on the same machine as Anki.
DEFAULT_URL = "http://127.0.0.1:8765"

# The version of the API this client speaks.
API_VERSION = 6

# A big collection can take a moment to answer; half a minute is a hung Anki.
TIMEOUT = 30


class AnkiConnectError(Exception):
    """Anki cannot be reached, or refused what it was asked to do."""


class AnkiConnect:
    """The actions this tool uses, against one AnkiConnect endpoint."""

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self.url = url

    def decks(self) -> list[str]:
        return self._call("deckNames")

    def note_types(self) -> list[str]:
        return self._call("modelNames")

    def note_type_fields(self, name: str) -> list[str]:
        """The fields of one note type, in the order the collection holds them."""
        return self._call("modelFieldNames", modelName=name)

    def note_type_templates(self, name: str) -> dict[str, dict[str, str]]:
        """One note type's cards, each against the two sides it renders."""
        return self._call("modelTemplates", modelName=name)

    def create_note_type(
        self,
        name: str,
        *,
        fields: Sequence[str],
        front: str,
        back: str,
        css: str,
    ) -> None:
        """Make a cloze note type carrying the card's design."""
        self._call(
            "createModel",
            modelName=name,
            inOrderFields=list(fields),
            cardTemplates=[{"Name": "Cloze", "Front": front, "Back": back}],
            css=css,
            isCloze=True,
        )

    def store_media(self, path: Path) -> str:
        """Give Anki the file at `path`, under the name it already has."""
        return self._call("storeMediaFile", filename=path.name, path=str(path))

    def add_note(
        self, *, deck: str, note_type: str, fields: dict[str, str], tags: Sequence[str]
    ) -> int:
        """Add one note, and answer the identifier Anki gave it."""
        return self._call(
            "addNote",
            note={
                "deckName": deck,
                "modelName": note_type,
                "fields": dict(fields),
                "tags": list(tags),
            },
        )

    def _call(self, action: str, **params: Any) -> Any:
        request = Request(
            self.url,
            data=json.dumps(
                {"action": action, "version": API_VERSION, "params": params}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                answer = json.load(response)
        except (OSError, ValueError) as error:
            raise AnkiConnectError(
                f"cannot reach AnkiConnect at {self.url} ({error}); is Anki running "
                "with the AnkiConnect add-on installed?"
            ) from error
        if answer.get("error"):
            raise AnkiConnectError(str(answer["error"]))
        return answer.get("result")
