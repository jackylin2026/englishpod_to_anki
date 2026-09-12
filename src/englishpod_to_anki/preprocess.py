"""Turning one lesson's PDF into the Markdown that sits between the stages.

The Markdown is where an extraction mistake can be read and corrected once,
rather than inherited by every card built from it, so it is written plainly
enough to be edited by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable
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
    Dialogue,
    Lesson,
    LessonError,
    Turn,
    VocabularyTerm,
    lesson_file,
    lesson_files,
    lesson_markdown,
    lesson_markdowns,
    read_markdown,
    render_dialogue,
    render_markdown,
    same_dialogue,
    transcript_file,
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


# What the OCR pass is to this stage: something that reads a lesson's rows back
# out of a page that holds no text, and nothing else about it.
Reader = Callable[[Path], list[Row]]

# What a document's lesson starts are asked of one row and the row below it:
# whether the one above is the rest of the title the other carries. A document
# that prints its titles its own way answers with a rule of its own.
TitleLine = Callable[[Row, Row], bool]

# What the print transcript is to this stage: something that says what one
# lesson's dialogue reads as in that printing, by the lesson's number, and
# nothing else about it. A lesson the transcript does not cover answers with
# nothing, which is not the same as answering with no dialogue.
Transcript = Callable[[str], Dialogue | None]


@dataclass(frozen=True)
class CrossCheck:
    """What the print transcript's version of one lesson's dialogue came to."""

    code: str
    file: Path
    written: bool
    differs: bool


@dataclass(frozen=True)
class Preprocessed:
    """What preprocess did with one lesson."""

    markdown: Path
    written: bool
    check: CrossCheck | None = None


def preprocess_lesson(
    lesson_dir: Path,
    *,
    force: bool = False,
    reader: Reader | None = None,
    transcript: Transcript | None = None,
) -> Preprocessed:
    """Write the lesson's Markdown beside its PDF -- or into its directory when
    the lesson is not in that PDF at all.

    Above 250 the corpus keeps an introduction sheet where a lesson's own PDF
    would be, and the lessons themselves in the batch's PDF one directory up, so
    a lesson the sheet carries no code for is read out of the PDF beside it.

    A lesson whose PDF holds no text at all is one preprocess cannot read, and
    says so -- unless a `reader` is given, which is the OCR pass, and then the
    lesson is read back out of the page's pictures instead.

    An existing Markdown file is left alone unless `force`, so that a hand
    correction survives a re-run.

    With a `transcript` -- the print transcript, which says what a lesson's
    dialogue reads as in that printing -- the transcript's version is written
    beside the Markdown, and the two are compared. The comparison changes
    nothing: it is reported, and the lesson is the same lesson either way.
    """
    pdf = lesson_file(lesson_dir, "*.pdf", what="PDF")
    held = lesson_markdowns(lesson_dir)
    # A lesson holds one Markdown, whatever its owner called it: the one that is
    # there is the one a re-run writes to, rather than a second file beside it.
    markdown = lesson_markdown(lesson_dir) if held else pdf.with_suffix(".md")
    if markdown.exists() and not force:
        return _checked(markdown, written=False, transcript=transcript, force=force)

    rows = read_rows(pdf)
    scanned = not rows
    if scanned and reader is not None:
        rows = reader(pdf)
        if not rows:
            # A page the service read nothing off is not one to describe as
            # needing the pass that has just read it.
            raise LessonError(f"the OCR pass read no text off {pdf}")
    if not rows:
        raise LessonError(f"{pdf} has no text layer; it needs the OCR pass")

    lesson = lesson_in(rows)
    if lesson is None:
        if scanned:
            # Nothing beside a page of pictures carries the lesson: what the OCR
            # pass made of it is all there is, so it is not looked for further.
            raise LessonError(f"{pdf} carries no lesson code")
        lesson = lesson_in(_lesson_beside(lesson_dir, pdf))
        if lesson is None:  # a slice of a batch begins at a lesson code
            raise LessonError(f"{pdf} carries no lesson code")
        if not held:
            # No PDF of its own to name the Markdown after, so it is named for
            # the code the lesson was found by, as every other stage names it.
            markdown = lesson_dir / f"englishpod_{lesson.code}.md"

    markdown.write_text(render_markdown(lesson), encoding="utf-8")
    return _checked(markdown, written=True, transcript=transcript, force=force)


def _checked(
    markdown: Path, *, written: bool, transcript: Transcript | None, force: bool
) -> Preprocessed:
    """One lesson done, with the print transcript's version of it checked.

    A lesson the transcript does not cover is not checked and gets no file beside
    it: the print holds no dialogue for it, so there is nothing to compare and
    nothing to report either. What the check reads is the lesson's own Markdown,
    so that a correction made to it by hand is the dialogue the lesson is
    checked with -- and the lesson is one a run may now report for what is wrong
    with its Markdown, where it used to be left alone unread.
    """
    if transcript is None:
        return Preprocessed(markdown=markdown, written=written)
    lesson = read_markdown(markdown)
    theirs = transcript(lesson.code[1:])
    if theirs is None:
        return Preprocessed(markdown=markdown, written=written)
    beside = transcript_file(markdown)
    # Written once and left alone after, as the Markdown itself is: the file is
    # the print's reading of the lesson rather than the run's, and `--force` is
    # what asks for it again.
    wrote = force or not beside.exists()
    if wrote:
        beside.write_text(render_dialogue(theirs), encoding="utf-8")
    return Preprocessed(
        markdown=markdown,
        written=written,
        check=CrossCheck(
            code=lesson.code,
            file=beside,
            written=wrote,
            differs=not same_dialogue(lesson.dialogue, theirs),
        ),
    )


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

    code, dialogue = dialogue_in(rows[:first_table_at] if first_table_at is not None else rows)
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
    every other lesson. A batch holds its lessons in one document, so what comes
    back is the slice belonging to this one.

    Every PDF beside the lesson is tried, because the one that carries it is not
    always the first: a batch keeps a per-lesson PDF here and there as well as
    its own. A PDF that cannot be read is passed over rather than reported in
    the lesson's place -- unless none of them carries the lesson, in which case
    what went wrong with one of them is the likelier answer.
    """
    trouble: LessonError | None = None
    for candidate in lesson_files(lesson_dir.parent, "*.pdf"):
        try:
            rows = _rows(candidate)
        except LessonError as error:
            trouble = trouble or error
            continue
        found = lesson_rows(rows, lesson_dir.name)
        if found:
            return found
    if trouble is not None:
        raise trouble
    raise LessonError(
        f"{pdf} carries no lesson code, and no PDF in {lesson_dir.parent} carries "
        f"lesson {lesson_dir.name}"
    )


def _is_title_line(above: Row, below: Row) -> bool:
    """Whether a row is the first line of the title the row below it carries.

    The rest of a title sits one line's height above the line holding the code,
    and is one run of words: a row of a vocabulary table would show the gaps
    between its columns. It also has to be above: the row before a lesson's first
    one in a document printed in columns is the previous column's last line, and
    a height measured upwards is a height no line can sit at.
    """
    if above.page != below.page or not 0 < below.top - above.top <= TITLE_LINE_HEIGHT:
        return False
    return all(b.x0 - a.x1 < MIN_GUTTER for a, b in zip(above.words, above.words[1:]))


def lessons_in(
    rows: list[Row], *, title_line: TitleLine = _is_title_line, code: re.Pattern[str] = CODE
) -> list[tuple[str, list[Row]]]:
    """One document's rows split by lesson, in the order the document holds them.

    A lesson begins at its title and ends where the next lesson's begins, and it
    is answered for by its number: the digits it prints, which is what says which
    lesson is meant when a document prints the rest of the code its own way --
    the print transcript's level letters are the print's, not the corpus's, and
    its digits are the print's too, two of its lessons being printed `(D046)` and
    `(C068)` for lessons 0046 and 0068.

    What a document's own title looks like, and what its codes look like, are the
    document's business: `title_line` and `code` are what it is asked. Getting
    the title wrong is expensive in a quiet way: a title line spans the columns
    of a vocabulary table, and one left at the end of the lesson before takes its
    columns with it, flattening that lesson's tables into one cell.
    """
    starts = _lesson_starts(rows, title_line, code)
    return [
        (
            code[1:],
            rows[start : starts[position + 1][0] if position + 1 < len(starts) else len(rows)],
        )
        for position, (start, code) in enumerate(starts)
    ]


def lesson_rows(rows: list[Row], number: str) -> list[Row] | None:
    """One lesson's rows out of a document holding several, or None if none is it."""
    for found, lesson in lessons_in(rows):
        if found == number:
            return lesson
    return None


def _lesson_starts(
    rows: list[Row], title_line: TitleLine, code: re.Pattern[str]
) -> list[tuple[int, str]]:
    """Where each lesson in a document begins, and the code it begins with.

    The walk back over a title's first line never reaches the lesson before:
    what it may take is bounded by the row the previous lesson's code is on, so
    one lesson's slice can neither overlap the last one's nor come out empty.
    """
    begins: list[tuple[int, str]] = []
    previous_code = -1
    for index, row in enumerate(rows):
        found = code.search(row.text)
        if found is None:
            continue
        start = index
        while start > previous_code + 1 and title_line(rows[start - 1], rows[start]):
            start -= 1
        begins.append((start, found.group(1)))
        previous_code = index
    return begins


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


def dialogue_in(rows: list[Row]) -> tuple[str | None, tuple[Turn, ...]]:
    """The lesson code from the title block, and the dialogue.

    The dialogue is one turn per speaker, each turn keeping the physical lines
    the page broke it into, so that the card built from it breaks where the page
    broke. A lesson can carry a code without carrying any dialogue, so the code
    is read from the whole title block rather than only up to the first speaker.
    """
    found = CODE.search(" ".join(row.text for row in rows))
    # A level letter is capitalised in the corpus, and read off a picture it
    # comes back however the shape of it struck the service. The code is the
    # note's identity, so it is the corpus's spelling that is kept: a lesson
    # read by OCR and one read out of a text layer are the same lesson.
    code = found.group(1).upper() if found else None

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
