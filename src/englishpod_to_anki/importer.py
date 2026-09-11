"""Sending a lesson's note to a running Anki.

Import is the only stage that touches the collection, and it does so through
AnkiConnect: it checks the deck it is writing into is there, makes the note type
if the collection lacks it, uploads the dialogue audio, and adds the note. A
lesson already in the collection is not this stage's business -- deciding what
to do about one is a later concern.
"""

from __future__ import annotations

from .anki import DEFAULT_URL, AnkiConnect, AnkiConnectError
from .card import BACK_TEMPLATE, CSS, FIELDS, FRONT_TEMPLATE, Note


def send_note(note: Note, *, url: str = DEFAULT_URL) -> int:
    """Put one lesson's note into the collection, and answer Anki's id for it."""
    anki = AnkiConnect(url)
    if note.deck not in anki.decks():
        raise AnkiConnectError(
            f"the {note.deck} deck is not in the collection; make it in Anki first"
        )
    if note.note_type not in anki.note_types():
        anki.create_note_type(
            note.note_type,
            fields=FIELDS,
            front=FRONT_TEMPLATE,
            back=BACK_TEMPLATE,
            css=CSS,
        )
    # The audio goes up before the note that plays it, or the field would point
    # at a file the collection does not have yet.
    anki.store_media(note.audio)
    return anki.add_note(
        deck=note.deck, note_type=note.note_type, fields=note.fields, tags=note.tags
    )
