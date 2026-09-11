"""Turning one lesson's PDF into the Markdown that sits between the stages.

The Markdown is where an extraction mistake can be read and corrected once,
rather than inherited by every card built from it, so it is written plainly
enough to be edited by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .layout import (
    MIN_GUTTER,
    Row,
    cell,
    columns,
    heal_wrapped_words,
    read_rows,
    term_rows,
)
from .lesson import (
    Lesson,
    LessonError,
    Turn,
    VocabularyTerm,
    lesson_file,
    lesson_files,
    render_markdown,
)

# The lesson code printed inside the PDF, which the filename may disagree with.
CODE = re.compile(r"\(([A-Za-z]\d{4})\)")

# How far above the row carrying a lesson code the rest of its title may sit.
TITLE_LINE_HEIGHT = 30.0

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
    """Write the lesson's Markdown beside its PDF -- or into its directory when
    the lesson is not in that PDF at all.

    Above 250 the corpus keeps an introduction sheet where a lesson's own PDF
    would be, and the lessons themselves in the batch's PDF one directory up, so
    a lesson the sheet carries no code for is read out of the PDF beside it.

    An existing Markdown file is left alone unless `force`, so that a hand
    correction survives a re-run.
    """
    pdf = lesson_file(lesson_dir, "*.pdf", what="PDF")
    held = lesson_files(lesson_dir, "*.md")
    # A lesson holds one Markdown, whatever its owner called it: the one that is
    # there is the one a re-run writes to, rather than a second file beside it.
    markdown = (
        lesson_file(lesson_dir, "*.md", what="Markdown") if held else pdf.with_suffix(".md")
    )
    if markdown.exists() and not force:
        return Preprocessed(markdown=markdown, written=False)

    lesson = lesson_in(_rows(pdf))
    if lesson is None:
        lesson = lesson_in(_lesson_beside(lesson_dir, pdf))
        if lesson is None:  # a slice of a batch begins at a lesson code
            raise LessonError(f"{pdf} carries no lesson code")
        if not held:
            # No PDF of its own to name the Markdown after, so it is named for
            # the code the lesson was found by, as every other stage names it.
            markdown = lesson_dir / f"englishpod_{lesson.code}.md"

    markdown.write_text(render_markdown(lesson), encoding="utf-8")
    return Preprocessed(markdown=markdown, written=True)


def _rows(path: Path) -> list[Row]:
    """A PDF's rows. Raises `LessonError` if it holds no readable text.

    A PDF this stage cannot read is named in full: a run over a corpus reports
    the lessons it skipped, and a file name alone would not say which of them.
    """
    rows = read_rows(path)
    if not rows:
        raise LessonError(f"{path} has no text layer; it needs the OCR pass")
    return rows


def lesson_in(rows: list[Row]) -> Lesson | None:
    """The lesson a document's rows hold, or None when they hold no lesson.

    A document carrying no lesson code is not a lesson: an introduction sheet,
    or one of the transcripts the corpus keeps beside the lessons. Reading one
    is how a stage that has a lesson directory knows whether the PDF in it is
    the lesson's.
    """
    key_at = _heading(rows, KEY_HEADING)
    supplementary_at = _heading(rows, SUPPLEMENTARY_HEADING)
    # A lesson with no Key Vocabulary table still has a Supplementary one, so the
    # title block ends at whichever heading comes first.
    first_table_at = min(
        (index for index in (key_at, supplementary_at) if index is not None), default=None
    )

    code, dialogue = _dialogue(rows[:first_table_at] if first_table_at is not None else rows)
    if code is None:
        return None
    return Lesson(
        code=code,
        dialogue=dialogue,
        key_vocabulary=_table(_section(rows, key_at, supplementary_at)),
        supplementary_vocabulary=_table(_section(rows, supplementary_at, None)),
    )


def _lesson_beside(lesson_dir: Path, pdf: Path) -> list[Row]:
    """The lesson's rows, from the PDF beside it that carries the lesson.

    The lesson is looked for by the number its directory is named with, which is
    where the lesson is rather than what it is: the code the card is identified
    by is read from inside the document the lesson is found in, as it is for
    every other lesson. A batch holds its ten lessons in one document, so what
    comes back is the slice belonging to this one.
    """
    for candidate in lesson_files(lesson_dir.parent, "*.pdf"):
        found = lesson_rows(_rows(candidate), lesson_dir.name)
        if found is not None:
            return found
    raise LessonError(
        f"{pdf} carries no lesson code, and no PDF in {lesson_dir.parent} carries "
        f"lesson {lesson_dir.name}"
    )


def lesson_rows(rows: list[Row], number: str) -> list[Row] | None:
    """One lesson's rows out of a document holding several, or None if none is it.

    A lesson begins at its title and ends where the next lesson's begins. The
    title is not always one row: a title too long for its column prints on two,
    and the code is beside the second -- so the row the code is on is walked
    back over the line above it when that line is the rest of the same title.
    Getting this wrong is expensive in a quiet way: a title line spans the
    columns of a vocabulary table, and one left at the end of the lesson before
    takes its columns with it, flattening that lesson's tables into one cell.
    """
    starts = _lesson_starts(rows)
    for position, (start, code) in enumerate(starts):
        if code[1:] != number:
            continue
        return rows[start : starts[position + 1][0] if position + 1 < len(starts) else len(rows)]
    return None


def _lesson_starts(rows: list[Row]) -> list[tuple[int, str]]:
    """Where each lesson in a document begins, and the code it begins with."""
    begins: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        found = CODE.search(row.text)
        if found is None:
            continue
        start = index
        while start and _is_title_line(rows[start - 1], rows[start]):
            start -= 1
        begins.append((start, found.group(1)))
    return begins


def _is_title_line(above: Row, below: Row) -> bool:
    """Whether a row is the first line of the title the row below it carries.

    The rest of a title sits one line's height above the line holding the code,
    and is one run of words: a row of a vocabulary table would show the gaps
    between its columns.
    """
    if above.page != below.page or below.top - above.top > TITLE_LINE_HEIGHT:
        return False
    return all(b.x0 - a.x1 < MIN_GUTTER for a, b in zip(above.words, above.words[1:]))


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
