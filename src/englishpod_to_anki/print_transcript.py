"""The print transcript: a second printing of many lessons' dialogues.

The corpus keeps a condensed printing of its dialogue beside the lessons
themselves -- a document of two columns to a page, holding dialogues for most of
the first three hundred and thirty lessons and no vocabulary at all. What it is
for here is the cross-check: split into one dialogue per lesson, it says what a
lesson's dialogue reads as in a printing that did not come from the lesson's own
document, so that an extraction can be compared against something other than
itself.

Two things about it are not true of a lesson's PDF. Its pages are printed in
columns, so a line belongs to the column it sits in rather than to the row it
shares a height with (`layout.read_columns` reads it that way). And the lesson a
dialogue belongs to is named by the number its code prints: the print letters
those codes its own way -- `C0003` where the corpus's documents say `B0003`, and
`(D046)` for lesson 0046 -- and it is the number that says which lesson is meant,
as it is for a lesson read out of a batch's PDF. The code a card is identified by
is read inside the lesson's own document, always.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .layout import Row, read_columns
from .lesson import Dialogue, LessonError
from .preprocess import KEY_HEADING, dialogue_in, lessons_in

# The code the print puts beside a lesson's title, which is its own printing of
# it rather than the corpus's: its level letters differ for seven lessons, and
# two of its codes are printed with three digits (`(D046)` for lesson 0046 and
# `(C068)` for 0068). What it says either way is the lesson's number.
CODE = re.compile(r"\(([A-Za-z]\d{1,4})\)")


@dataclass(frozen=True)
class PrintTranscript:
    """What the print transcript prints, one dialogue to a lesson.

    A lesson is held by its number rather than by the whole code it prints, so
    that asking for one is asking the same way whichever printing of that code a
    lesson's own document carries.
    """

    dialogues: Mapping[str, Dialogue]

    def dialogue(self, number: str) -> Dialogue | None:
        """What one lesson's dialogue reads as in the print, or None if none is it.

        A dialogue the print holds no turns for is no dialogue: a lesson the
        document names and prints nothing under is one it does not cover.
        """
        return self.dialogues.get(number) or None


def read(path: Path) -> PrintTranscript:
    """The print transcript a document holds.

    Raises `LessonError` for a document that is not one -- one that cannot be
    read, one that carries vocabulary, or one that prints no lesson at all --
    rather than answering with no lessons and letting a run check nothing.
    """
    rows = read_columns(path)
    if any(row.squashed == KEY_HEADING for row in rows):
        raise LessonError(f"{path} carries vocabulary; it is not the print transcript")
    dialogues = _dialogues(rows)
    if not dialogues:
        raise LessonError(f"{path} carries no lesson code, so it is not the print transcript")
    return PrintTranscript(dialogues)


def _dialogues(rows: list[Row]) -> dict[str, Dialogue]:
    """One dialogue per lesson number the document prints, in the order it prints them.

    The number is written as the four digits a lesson's code carries, whatever
    the print's own run of digits is: `(D046)` is lesson 0046's, and asking for a
    lesson asks the same way of every printing of its code.
    """
    titles = _title_sizes(rows)
    found: dict[str, Dialogue] = {}
    for printed, block in lessons_in(rows, code=CODE):
        _, dialogue = dialogue_in(_without_the_titles(block, titles))
        if dialogue:
            found[f"{int(printed):04d}"] = dialogue
    return found


def _title_sizes(rows: list[Row]) -> set[float | None]:
    """The sizes the print sets a lesson's title in, read off the rows carrying codes."""
    return {word.size for row in rows if CODE.search(row.text) for word in row.words}


def _without_the_titles(block: list[Row], titles: set[float | None]) -> list[Row]:
    """One lesson's rows with its title taken out of them.

    A lesson's title is set in a size of its own -- the size the row carrying its
    code is set in -- and a title outlives the code row that would have placed it:
    the print fills a column and breaks it wherever it fills, so a title of its
    two-line kind is often split across the break, with its first line left at the
    end of the lesson before. A row set in the title's size is a title wherever it
    falls, so dropping those rows is what keeps a lesson's title out of the
    dialogue of the lesson before it.

    A reading with no sizes to give -- a page read back off a picture by the OCR
    pass has none, though nothing this tool reads a transcript with does -- is
    left as it stands.
    """
    if not titles - {None}:
        return block
    return [row for row in block if all(word.size not in titles for word in row.words)]
