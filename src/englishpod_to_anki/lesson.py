"""The lesson as Markdown: what one stage writes and the next one reads.

The Markdown sits deliberately between extraction and card-building, so it is
also the contract between them: preprocess writes it and build reads it, and
neither stage reaches into the other. Reading a lesson back is therefore written
beside the code that writes it, and both directions meet in one shape -- as does
what a lesson directory has to hold for either stage to work on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The heading each part of a lesson sits under, and a table's three columns.
DIALOGUE = "Dialogue"
KEY_VOCABULARY = "Key Vocabulary"
SUPPLEMENTARY_VOCABULARY = "Supplementary Vocabulary"
TERM, PART_OF_SPEECH, DEFINITION = "term", "part of speech", "definition"

# What an escaped pipe reads as inside a cell, so that a term or definition
# carrying one survives the round trip through a Markdown table.
ESCAPED_PIPE = "\\|"


class LessonError(Exception):
    """The lesson is not one the stages can work with, so nothing was done.

    A lesson directory holding no PDF, two of them, or no Markdown; a lesson
    whose code cannot be found; a Markdown file not in the shared form. Every
    stage reports these the same way, and none of them is a crash.
    """


@dataclass(frozen=True)
class VocabularyTerm:
    """One row of a vocabulary table: a term, a part of speech and a definition."""

    term: str
    part_of_speech: str
    definition: str


# One speaker's turn: the physical lines the page broke it into, in order.
Turn = tuple[str, ...]

# A whole dialogue: one turn per speaker, in the order they speak.
Dialogue = tuple[Turn, ...]


@dataclass(frozen=True)
class Lesson:
    """What one lesson holds, whichever stage read it.

    A lesson without a code is not a `Lesson`: every stage refuses one, because
    the code is the name the corpus knows the lesson by.
    """

    code: str
    dialogue: Dialogue
    key_vocabulary: tuple[VocabularyTerm, ...]
    supplementary_vocabulary: tuple[VocabularyTerm, ...]


def lesson_file(directory: Path, name: str, *, what: str) -> Path:
    """The one file of its kind a lesson directory holds.

    A lesson directory holds one PDF, one Markdown file and one dialogue
    recording. Two of any of them is a directory the tool declines to guess
    about, rather than one it picks a file out of.
    """
    if not directory.is_dir():
        raise LessonError(f"{directory} is not a directory")
    files = sorted(directory.glob(name))
    if not files:
        raise LessonError(f"{directory} holds no {what}")
    if len(files) > 1:
        names = ", ".join(file.name for file in files)
        raise LessonError(f"{directory} holds more than one {what}: {names}")
    return files[0]


def render_markdown(lesson: Lesson) -> str:
    """The Markdown form of a lesson, as the build stage will read it."""
    lines = [f"# {lesson.code}", "", f"## {DIALOGUE}", ""]
    for turn in lesson.dialogue:
        lines += [*turn, ""]
    for heading, table in (
        (KEY_VOCABULARY, lesson.key_vocabulary),
        (SUPPLEMENTARY_VOCABULARY, lesson.supplementary_vocabulary),
    ):
        lines += [f"## {heading}", "", "| Term | Part of speech | Definition |", "| --- | --- | --- |"]
        lines += [
            f"| {_escape(term.term)} | {_escape(term.part_of_speech)} | {_escape(term.definition)} |"
            for term in table
        ]
        lines.append("")
    return "\n".join(lines).strip("\n") + "\n"


def read_markdown(path: Path) -> Lesson:
    """The lesson a Markdown file holds.

    Raises `LessonError` if the file cannot be read, or carries no title, which
    is where the lesson code every stage names the lesson by is read from.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LessonError(f"cannot read {path}: {error.strerror}") from error

    title, sections = _sections(text)
    code = _code(title)
    if code is None:
        raise LessonError(f"{path.name} carries no lesson code")
    return Lesson(
        code=code,
        dialogue=_dialogue(sections.get(DIALOGUE, "")),
        key_vocabulary=_table(sections.get(KEY_VOCABULARY, "")),
        supplementary_vocabulary=_table(sections.get(SUPPLEMENTARY_VOCABULARY, "")),
    )


def _sections(text: str) -> tuple[str, dict[str, str]]:
    """The title line, and each `## heading` against the text under it."""
    title = ""
    sections: dict[str, str] = {}
    heading: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            sections[heading] = ""
        elif heading is None:
            title += line + "\n"
        else:
            sections[heading] += line + "\n"
    return title, sections


def _code(title: str) -> str | None:
    """The lesson code the title carries."""
    for line in title.splitlines():
        if line.startswith("# "):
            code = line[2:].strip()
            if code:
                return code
    return None


def _dialogue(body: str) -> tuple[Turn, ...]:
    """A section's paragraphs, each the physical lines one speaker's turn kept."""
    turns: list[list[str]] = [[]]
    for line in body.splitlines():
        if line.strip():
            turns[-1].append(line.rstrip())
        else:
            turns.append([])
    return tuple(tuple(turn) for turn in turns if turn)


def _table(body: str) -> tuple[VocabularyTerm, ...]:
    """A Markdown table's data rows, read by column name rather than position."""
    rows = [_cells(line) for line in body.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return ()
    columns = {name.strip().lower(): index for index, name in enumerate(rows[0])}
    return tuple(
        VocabularyTerm(
            term=_column(row, columns, TERM),
            part_of_speech=_column(row, columns, PART_OF_SPEECH),
            definition=_column(row, columns, DEFINITION),
        )
        for row in rows[1:]
        if not _is_rule(row)
    )


def _is_rule(row: list[str]) -> bool:
    """Whether a row is the `| --- | --- |` line under a table's header."""
    return all(cell.strip("-: ") == "" and cell.strip() for cell in row)


def _cells(line: str) -> list[str]:
    """One table row's cells, splitting only on pipes that are not escaped."""
    fields: list[str] = []
    cell = ""
    escaped = False
    for character in line.strip().strip("|"):
        if escaped:
            cell += character
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            fields.append(cell.strip())
            cell = ""
        else:
            cell += character
    fields.append(cell.strip())
    return fields


def _column(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    return row[index] if index is not None and index < len(row) else ""


def _escape(text: str) -> str:
    return text.replace("|", ESCAPED_PIPE)
