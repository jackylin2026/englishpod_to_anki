"""Importing a lesson into a running Anki, and what to do about the ones there.

Import is the only stage that touches the collection, and it does so through
AnkiConnect: it checks the deck it is writing into is there, makes the note type
if the collection lacks it, uploads the dialogue audio, and adds the note.

A lesson the collection already holds is not the tool's to decide about: the
note there may be one the learner has studied for months. The run asks what to
do about it -- leave it, or refresh it and keep the review history it has earned
-- and one answer can be given for every lesson left, so that a corpus-wide
re-run is a single decision. A flag answers ahead of time, for a run with nobody
watching to answer it.

Everything a run learns about the collection is learnt once, before the first
note is written: what the deck holds is read there rather than asked per lesson,
and a lesson already in it is settled by that reading rather than by Anki
refusing a note the tool should not have tried to make.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .anki import DEFAULT_URL, AnkiConnect, AnkiConnectError
from .card import (
    BACK_TEMPLATE,
    CSS,
    FIELDS,
    FRONT_TEMPLATE,
    SENTENCES,
    TTS,
    Note,
    design_differences,
    plain_dialogue,
    recordings,
)
from .lesson import LessonError

# What a run does about a lesson the collection already holds: ask, leave the
# lesson exactly as it is, or refresh the note that is there.
ASK, SKIP, REPLACE = "ask", "skip", "replace"
POLICIES = (ASK, SKIP, REPLACE)

# What import did with a lesson: added a note the collection did not have,
# refreshed the one it had, or left that one exactly as it was.
IMPORTED, REFRESHED, LEFT = "imported", "refreshed", "left"

# A note's identity is the tag it is born with, `englishpod::C0108` (ADR-0004).
# The lesson code a note stands for is that tag with this prefix taken off.
IDENTITY = "englishpod::"

# How a note already in the collection was recognised as a lesson's: by the tag
# a note the tool made carries, by the dialogue recording it plays, or by the
# words of the dialogue a note made by hand holds.
BY_TAG, BY_RECORDING, BY_DIALOGUE = "its tag", "its dialogue recording", "its dialogue"


class Unanswered(Exception):
    """A run asked what to do about a lesson already there, and nobody answered.

    A run with no one at the keyboard -- in a script, or with its input at an
    end of file -- must not sit waiting on a question, so it says what it was
    asked and what to pass instead of asking again.
    """


@dataclass(frozen=True)
class Present:
    """A lesson's note, already in the collection."""

    note_id: int
    note_type: str
    by: str


@dataclass(frozen=True)
class Done:
    """What import did with one lesson. The note is the one the lesson now has."""

    code: str
    what: str
    note_id: int


class Importer:
    """One run's conversation with the collection it is writing into."""

    def __init__(self, *, url: str = DEFAULT_URL, policy: str = ASK, many: bool = False) -> None:
        self.anki = AnkiConnect(url)
        self.policy = policy
        # Whether the run holds more lessons than the one being asked about: a
        # corpus-wide re-run is where one answer for all the rest is worth
        # taking, and a single lesson is where there are no rest to answer for.
        self.many = many
        self.decided: str | None = None
        self.by_code: dict[str, list[Present]] = {}
        self.by_recording: dict[str, Present] = {}
        self.by_dialogue: dict[str, Present] = {}
        self.ready = False

    def send(self, note: Note) -> Done:
        """Put one lesson's note in the collection, or leave what is there."""
        self._prepare(note)
        present = self._present(note)
        if present is None:
            return self._add(note)
        if self._answer(note, present) == SKIP:
            return Done(code=note.code, what=LEFT, note_id=present.note_id)
        return self._replace(note, present)

    def _prepare(self, note: Note) -> None:
        """Settle that the collection is one to write into, and read what it holds."""
        if self.ready:
            return
        if note.deck not in self.anki.decks():
            raise AnkiConnectError(
                f"the {note.deck} deck is not in the collection; make it in Anki first"
            )
        self._ensure_note_type(note)
        self._read(note.deck)
        self.ready = True

    def _ensure_note_type(self, note: Note) -> None:
        """Make the card's note type, or check the one that is there is the design."""
        if note.note_type not in self.anki.note_types():
            self.anki.create_note_type(
                note.note_type,
                fields=FIELDS,
                front=FRONT_TEMPLATE,
                back=BACK_TEMPLATE,
                css=CSS,
            )
            return
        # A note type of the right name may still be a different card: one made
        # by hand, or by an earlier design. Its fields are checked before a note
        # is shaped to fit them, and its cards before the note would render in
        # them -- a field the type lacks is dropped from a note without a word.
        if differences := self._differences(note.note_type):
            raise AnkiConnectError(
                f"the {note.note_type} note type in the collection is not the card's design "
                f"({'; '.join(differences)}); bring it into line in Anki, or delete it if it "
                "holds no notes, then run import again"
            )

    def _differences(self, note_type: str) -> tuple[str, ...]:
        """How a note type the collection holds differs from the card's design."""
        return design_differences(
            self.anki.note_type_fields(note_type),
            self.anki.note_type_templates(note_type),
        )

    def _read(self, deck: str) -> None:
        """The lessons the collection already holds, by tag, recording and dialogue.

        A note the tool made carries the lesson's code in its tag. One made by
        hand, or by an earlier program, carries nothing that can be searched
        for, and is recognised by what it holds instead: the dialogue recording
        it plays, which is the corpus's own file, and the words of the dialogue
        itself, whatever its maker chose to blank and punctuate.
        """
        for info in self.anki.notes_info(self.anki.find_notes(f'deck:"{deck}"')):
            if not info:
                # A note that was there when the deck was searched and is gone
                # by the time it is read. AnkiConnect answers an empty object
                # for it, which says nothing rather than not saying it.
                continue
            if code := _code_of(info["tags"]):
                # A tag is the note's identity, so two notes carrying one is a
                # contradiction to report rather than one of them to pick.
                self.by_code.setdefault(code, []).append(_present(info, BY_TAG))
            # A note is read for the other two as well, tagged or not: the code
            # in a tag is the one the lesson had when the note was made, and a
            # lesson re-read from another document can come out under another.
            for name in recordings(_field(info, TTS)):
                self.by_recording.setdefault(name, _present(info, BY_RECORDING))
            if dialogue := plain_dialogue(_field(info, SENTENCES)):
                self.by_dialogue.setdefault(dialogue, _present(info, BY_DIALOGUE))

    def _present(self, note: Note) -> Present | None:
        """The note the collection holds for a lesson, if it holds one.

        The lesson's tag is looked for first, since a note the tool made is
        known by it. Then the recording the note plays, which is the corpus's
        own file and names the lesson exactly. Then the dialogue itself: the
        lesson's words, in the order the lesson says them, whichever words the
        note's maker blanked and however they punctuated them.
        """
        if tagged := self.by_code.get(note.code):
            if len(tagged) > 1:
                raise LessonError(
                    f"the collection holds {len(tagged)} notes tagged "
                    f"{IDENTITY}{note.code}, and which of them to refresh is not the tool's to "
                    "guess; delete the ones you do not want in Anki, then run import again"
                )
            return tagged[0]
        if recorded := self.by_recording.get(note.audio.name):
            return recorded
        return self.by_dialogue.get(plain_dialogue(note.fields[SENTENCES]))

    def _answer(self, note: Note, present: Present) -> str:
        """What to do about a lesson already there, as the run comes to know it.

        An answer given for every lesson left is remembered here, which is what
        makes a corpus-wide re-run one decision rather than three hundred.
        """
        if self.decided is not None:
            return self.decided
        if self.policy != ASK:
            return self.policy
        return self._ask(note, present)

    def _ask(self, note: Note, present: Present) -> str:
        """Say what was found and what can be done about it, and take the answer.

        The choices are spelled out rather than left to a `[y/N]`, because this
        is the one question the tool asks about the learner's own collection and
        the two answers are not each other's opposite: one leaves the card
        alone, and one rewrites it.
        """
        prompt = "\n".join(
            [
                f"import: {note.code} is already in the collection "
                f"(note {present.note_id}, found by {present.by}).",
                "  [s]kip      leave the card, and its review history, as they are",
                "  [r]eplace   refresh the card's content, keeping its review history",
                f"{self._question()}: ",
            ]
        )
        while True:
            try:
                answer = input(prompt)
            except EOFError as error:
                raise Unanswered(
                    f"{note.code} is already in the collection and there is nobody to ask; "
                    "pass --existing skip or --existing replace to answer ahead of time"
                ) from error
            if (chosen := _chosen(answer)) is not None:
                verb, everyone = chosen
                if everyone:
                    self.decided = verb
                return verb
            # A mistyped answer is nobody's decision: the choices are shown
            # again rather than the least of them taken.
            print(f"import: {answer.strip()!r} is not one of the answers")

    def _question(self) -> str:
        """What the run is asking, as a line beneath the choices."""
        question = "answer s or r"
        if self.many:
            question += ', adding "all" to answer the same way for every lesson left'
        return question

    def _add(self, note: Note) -> Done:
        """Upload a lesson's audio, and add the note that plays it."""
        self.anki.store_media(note.audio)
        return Done(
            code=note.code,
            what=IMPORTED,
            note_id=self.anki.add_note(
                deck=note.deck,
                note_type=note.note_type,
                fields=note.fields,
                tags=note.tags,
            ),
        )

    def _replace(self, note: Note, present: Present) -> Done:
        """Refresh the note that is there, keeping the card it already made.

        The note keeps its identity, its deck and its tags, and its card keeps
        its scheduling and its review history: what changes is the content the
        card renders. Making the note again under the same identity would put a
        card the learner has never studied in place of one they have.
        """
        self._refuse_a_type_that_hides_the_card(note, present)
        self.anki.store_media(note.audio)
        self.anki.update_note_fields(present.note_id, note.fields)
        return Done(code=note.code, what=REFRESHED, note_id=present.note_id)

    def _refuse_a_type_that_hides_the_card(self, note: Note, present: Present) -> None:
        """Leave a note alone rather than write the card where it is not rendered.

        A note the tool made is of the tool's own note type, checked before
        anything is written. A note found by its dialogue may be of any type --
        the learner's own, or one made by something else -- so the type holding
        it is checked the same way before its note is refreshed. The lesson is
        reported and left alone, and the run carries on to the next one.
        """
        if present.note_type == note.note_type:
            return
        if differences := self._differences(present.note_type):
            raise LessonError(
                f"{note.code}: the {present.note_type} note type holding its card is not the "
                f"card's design ({'; '.join(differences)}); its card was left as it is"
            )


# The two answers the prompt takes, as a person types them: the letter or the
# whole word, so that neither has to be remembered exactly.
ANSWERS = {"s": SKIP, "skip": SKIP, "r": REPLACE, "replace": REPLACE}


def _chosen(answer: str) -> tuple[str, bool] | None:
    """Which of the two an answer picks, and whether it picks it for the rest too.

    `s` and `r` answer for one lesson; `s all` and `r all` answer for every
    lesson left, so that a run of three hundred lessons is one decision.
    """
    words = answer.strip().lower().split()
    if not words or len(words) > 2 or words[0] not in ANSWERS:
        return None
    if len(words) == 2 and words[1] != "all":
        return None
    return ANSWERS[words[0]], len(words) == 2


def _present(info: Mapping[str, Any], by: str) -> Present:
    """One note the collection holds, as the reading of the deck describes it."""
    return Present(note_id=info["noteId"], note_type=info["modelName"], by=by)


def _field(info: Mapping[str, Any], name: str) -> str:
    """What one field of a note holds, as the collection reports its fields."""
    return info["fields"].get(name, {}).get("value", "")


def _code_of(tags: Sequence[str]) -> str | None:
    """The lesson code a note's tags name, for a note the tool made.

    Only the tool's own notes carry one: a note made by hand, or by an earlier
    program, has no such tag and is found by the dialogue it holds instead.
    """
    for tag in tags:
        if tag.startswith(IDENTITY):
            return tag[len(IDENTITY) :]
    return None
