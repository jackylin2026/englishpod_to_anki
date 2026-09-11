"""Turning one lesson's PDF into the Markdown that sits between the stages.

The Markdown is where an extraction mistake can be read and corrected once,
rather than inherited by every card built from it, so it is written plainly
enough to be edited by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .layout import Row, cell, columns, heal_wrapped_words, read_rows, term_rows
from .lesson import Lesson, LessonError, Turn, VocabularyTerm, lesson_file, render_markdown

# The lesson code printed inside the PDF, which the filename may disagree with.
CODE = re.compile(r"\(([A-Za-z]\d{4})\)")

# A speaker label: one or two capitalised words at the start of a line, always
# followed by a colon. Most lessons use `A:` and `B:`, but some name their speakers.
SPEAKER = re.compile(r"^(?:[A-Z][A-Za-z.']*|[A-Z])(?: [A-Z][A-Za-z.']*)?:")

KEY_HEADING = "KeyVocabulary"
SUPPLEMENTARY_HEADING = "SupplementaryVocabulary"

# A vocabulary table's three columns, left to right.
TERM_COLUMN, PART_OF_SPEECH_COLUMN, DEFINITION_COLUMN = 0, 1, 2


@dataclass(frozen=True)
class Preprocessed:
    """What preprocess did with one lesson."""

    markdown: Path
    written: bool


def preprocess_lesson(lesson_dir: Path, *, force: bool = False) -> Preprocessed:
    """Write the lesson's Markdown beside its PDF.

    An existing Markdown file is left alone unless `force`, so that a hand
    correction survives a re-run.
    """
    pdf = lesson_file(lesson_dir, "*.pdf", what="PDF")
    markdown = pdf.with_suffix(".md")
    if markdown.exists() and not force:
        return Preprocessed(markdown=markdown, written=False)

    markdown.write_text(render_markdown(read_lesson(pdf)), encoding="utf-8")
    return Preprocessed(markdown=markdown, written=True)


def read_lesson(path: Path) -> Lesson:
    """Read one lesson PDF. Raises `LessonError` if it holds no readable text.

    A PDF this stage cannot read is named in full: a run over a corpus reports
    the lessons it skipped, and a file name alone would not say which of them.
    """
    rows = read_rows(path)
    if not rows:
        raise LessonError(f"{path} has no text layer; it needs the OCR pass")

    key_at = _heading(rows, KEY_HEADING)
    supplementary_at = _heading(rows, SUPPLEMENTARY_HEADING)
    # A lesson with no Key Vocabulary table still has a Supplementary one, so the
    # title block ends at whichever heading comes first.
    first_table_at = min(
        (index for index in (key_at, supplementary_at) if index is not None), default=None
    )

    code, dialogue = _dialogue(rows[:first_table_at] if first_table_at is not None else rows)
    if code is None:
        raise LessonError(f"{path} carries no lesson code")
    return Lesson(
        code=code,
        dialogue=dialogue,
        key_vocabulary=_table(_section(rows, key_at, supplementary_at)),
        supplementary_vocabulary=_table(_section(rows, supplementary_at, None)),
    )


def _heading(rows: list[Row], heading: str) -> int | None:
    for index, row in enumerate(rows):
        if row.squashed == heading:
            return index
    return None


def _section(rows: list[Row], start: int | None, stop: int | None) -> list[Row]:
    """The rows between two section headings, or none if the first is absent."""
    if start is None:
        return []
    return rows[start + 1 : stop if stop is not None else len(rows)]


def _dialogue(rows: list[Row]) -> tuple[str | None, tuple[Turn, ...]]:
    """The lesson code from the title block, and the dialogue.

    The dialogue is one turn per speaker, each turn keeping the physical lines
    the page broke it into, so that the card built from it breaks where the page
    broke. A lesson can carry a code without carrying any dialogue, so the code
    is read from the whole title block rather than only up to the first speaker.
    """
    found = CODE.search(" ".join(row.text for row in rows))
    code = found.group(1) if found else None

    first_turn = next((index for index, row in enumerate(rows) if SPEAKER.match(row.text)), None)
    if first_turn is None:
        return code, ()

    turns: list[list[str]] = [[rows[first_turn].text]]
    for row in rows[first_turn + 1 :]:
        if SPEAKER.match(row.text):
            turns.append([row.text])
        else:
            turns[-1].append(row.text)
    return code, tuple(tuple(heal_wrapped_words(turn)) for turn in turns)


def _table(rows: list[Row]) -> tuple[VocabularyTerm, ...]:
    if not rows:
        return ()
    edges = columns(rows)
    return tuple(
        VocabularyTerm(
            term=cell(group, edges, TERM_COLUMN),
            part_of_speech=cell(group, edges, PART_OF_SPEECH_COLUMN),
            definition=cell(group, edges, DEFINITION_COLUMN),
        )
        for group in term_rows(rows)
    )
