"""Recovering the physical layout of a lesson PDF.

A lesson PDF holds one column of dialogue followed by two three-column
vocabulary tables. Nothing in the file marks where a column begins, so the
geometry is recovered from where the words sit on the page.

Reading the words back out is part of the same job: the page breaks words and
prints contractions as several runs of glyphs, and putting them back together
needs to know where the columns end and what the words are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from .dictionary import is_word
from .lesson import LessonError

# Words whose tops are closer together than this sit on the same physical line.
ROW_TOLERANCE = 6.0

# A horizontal gap narrower than this is the space between two words, not
# between two columns.
MIN_GUTTER = 8.0

# A vertical gap this many times the table's own row pitch begins a new term.
TERM_GAP_FACTOR = 1.5

# A gap narrower than this is not a row pitch at all: a table read back off a
# picture has boxes a fraction of a point apart where a text layer has one line.
NARROWER_THAN_A_ROW = 6.0

# What an English contraction can end in once its apostrophe is taken off:
# I'm, you've, he's, don't, we'd, they'll, you're. Anything longer is a word in
# its own right that happens to open with an apostrophe.
CONTRACTION_TAILS = frozenset({"m", "s", "t", "d", "ll", "re", "ve"})

# Printed at the foot of every page of the corpus and belonging to no lesson.
FOOTER = re.compile(
    r"Visit.*OnlineReview.*Discussion.*textversion|PraxisLanguageLtd",
    re.IGNORECASE,
)

# Printed at the head of every page of the lessons as the corpus printed them,
# and belonging to no lesson either. The text layer the corpus also keeps does
# not carry it, but a page read back off its own picture does -- and a running
# head spans the whole width of the page, across the gaps between a vocabulary
# table's columns, so leaving it in flattens the table it sits above.
HEADER = re.compile(r"^EnglishPod$|LearnEnglishonyourTerms", re.IGNORECASE)


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float


@dataclass(frozen=True)
class Seen:
    """One word as it was found on a page: its text, and where it sat.

    A word is one either way it is found -- read out of the text layer, or read
    back out of a picture by the OCR pass -- so that both kinds arrive at the
    same rows, and the lesson read off them is read by the same code.
    """

    text: str
    top: float
    x0: float
    x1: float


@dataclass(frozen=True)
class Row:
    """One physical line of a page."""

    page: int
    top: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        """The row's words, in reading order."""
        return " ".join(word.text for word in self.words)

    @property
    def squashed(self) -> str:
        """The row's text with none of its spaces, for matching a printed phrase.

        The spaces are taken off a word's own text as well as the ones between
        words, because a row read back off a page arrives as whole printed lines
        rather than as words: a heading and a page's footer have to be matched
        the same way whichever kind of reading found them.
        """
        return "".join(self.text.split())


def read_rows(path: Path) -> list[Row]:
    """Every physical line of the PDF in reading order, page footers dropped.

    A file that is not a PDF this can open -- truncated, or not a PDF at all --
    is the lesson's problem rather than the run's, so it is reported the way
    every other unreadable lesson is: a run over a corpus skips that lesson and
    carries on, and a stage pointed at it says what is wrong rather than letting
    the library's error out as a traceback.
    """
    rows: list[Row] = []
    try:
        with pdfplumber.open(path) as pdf:
            for number, page in enumerate(pdf.pages):
                rows += page_rows(
                    number,
                    [
                        Seen(text=word["text"], top=word["top"], x0=word["x0"], x1=word["x1"])
                        for word in _words(page)
                    ],
                )
    except (OSError, PdfminerException) as error:
        raise LessonError(f"cannot read {path}: {error}") from error
    return rows


def page_rows(page: int, seen: Sequence[Seen]) -> list[Row]:
    """One page's words as its physical lines, the page's footer dropped.

    Where a line ends is what a card's own line breaks are made of, so this is
    the same work whether the words were read out of a text layer or off a
    picture: the two differ in how the words were found, not in what a line is.
    """
    rows: list[Row] = []
    for line in _by_top(seen):
        row = Row(
            page=page,
            top=max(word.top for word in line),
            words=tuple(
                _rejoin_apostrophes([Word(word.text, word.x0, word.x1) for word in line])
            ),
        )
        if not _trappings(row):
            rows.append(row)
    return rows


def _trappings(row: Row) -> bool:
    """Whether a row is the page's own furniture rather than the lesson's."""
    return bool(FOOTER.search(row.squashed) or HEADER.search(row.squashed))


def _rejoin_apostrophes(words: list[Word]) -> list[Word]:
    """Put back together a word the PDF printed as more than one run of glyphs.

    Contractions arrive in two broken shapes. The apostrophe can be a run of its
    own, so `I'll` comes as `I`, `'`, `ll`. Or it can be glued to what follows
    it, so `You've` comes as `You` and `'ve`.
    """
    rejoined: list[Word] = []
    apostrophe_alone = False
    for word in words:
        if rejoined and (
            apostrophe_alone or _is_stray_apostrophe(word) or _is_contraction_tail(word, rejoined[-1])
        ):
            last = rejoined[-1]
            rejoined[-1] = Word(last.text + word.text, last.x0, word.x1)
        else:
            rejoined.append(word)
        # Only an apostrophe we just took in as a fragment of its own wants what
        # follows it. A word that merely ends in one is a possessive, and the
        # next word is a word in its own right.
        apostrophe_alone = _is_stray_apostrophe(word)
    return rejoined


def _is_contraction_tail(word: Word, previous: Word) -> bool:
    """Whether this fragment continues a contraction cut before its apostrophe.

    `You've` can arrive as `You` and `'ve`. Only a contraction's tail is glued
    back on, so a word that really does open with an apostrophe -- `'tis`,
    `'bout` -- keeps the space in front of it.
    """
    tail = word.text.removeprefix("'").removeprefix("’")
    return (
        tail != word.text
        and tail.isalpha()
        and tail.lower() in CONTRACTION_TAILS
        and previous.text[-1:].isalpha()
    )


def _is_stray_apostrophe(word: Word) -> bool:
    return word.text != "" and word.text.strip("'’") == ""


def _words(page: pdfplumber.page.Page) -> list[dict[str, Any]]:
    """A page's words, grouped as the PDF itself laid them out.

    Reading the flow rather than the page geometry keeps a wide speaker label
    whole on the lessons where it overlaps the first word of what that speaker
    says. Both are drawn over each other, and ordering by position alone
    interleaves their letters.
    """
    return page.extract_words(use_text_flow=True)


def _by_top(seen: Sequence[Seen]) -> list[list[Seen]]:
    """Group a page's words into physical lines, left to right."""
    if not seen:
        return []
    ordered = sorted(seen, key=lambda word: (word.top, word.x0))
    lines = [[ordered[0]]]
    for word in ordered[1:]:
        if word.top - lines[-1][0].top <= ROW_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda word: word.x0) for line in lines]


def columns(rows: list[Row]) -> tuple[float, ...]:
    """The left edge of each column of a vocabulary table.

    The two widest gaps that stay empty down the whole table separate the
    columns. Narrower empty gaps are the stretched spaces of a justified line
    inside a cell, which can be wider than a column's own margin.
    """
    if not rows:
        return ()
    spans = sorted((word.x0, word.x1) for row in rows for word in row.words)
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gutters = sorted(
        (
            (merged[i + 1][0] - merged[i][1], merged[i + 1][0])
            for i in range(len(merged) - 1)
            if merged[i + 1][0] - merged[i][1] >= MIN_GUTTER
        ),
        reverse=True,
    )
    return (merged[0][0], *sorted(start for _width, start in gutters[:2]))


def _column_of(word: Word, edges: tuple[float, ...]) -> int:
    """Which column a word falls in, given the columns' left edges."""
    index = 0
    for position, edge in enumerate(edges):
        if word.x0 >= edge - 0.5:
            index = position
    return index


def term_rows(rows: list[Row]) -> list[list[Row]]:
    """Split a vocabulary table's rows into one group per vocabulary term.

    A term's own lines sit close together and the gap before the next term is
    wider. The pitch is the narrowest gap between two rows -- but a gap too
    narrow to be one is not a pitch: a table read back off a picture has a row
    whose two boxes sit a fraction of a point apart, and reading that off as the
    table's pitch made every row a term of its own, filling the tables of a
    third of the corpus's scans with empty-term rows. A page break always begins
    a new term.
    """
    if not rows:
        return []
    pitches = [
        following.top - current.top
        for current, following in zip(rows, rows[1:])
        if current.page == following.page and following.top > current.top
    ]
    pitches = [pitch for pitch in pitches if pitch >= NARROWER_THAN_A_ROW] or pitches
    threshold = min(pitches) * TERM_GAP_FACTOR if pitches else None

    groups: list[list[Row]] = [[rows[0]]]
    for current, following in zip(rows, rows[1:]):
        begins_term = (
            threshold is None
            or current.page != following.page
            or following.top <= current.top
            or following.top - current.top >= threshold
        )
        if begins_term:
            groups.append([following])
        else:
            groups[-1].append(following)
    return groups


def heal_wrapped_words(fragments: Iterable[str]) -> list[str]:
    """Fragments with any word the typesetter broke across two of them put back together.

    A fragment ending in a hyphen is a word split by a line break. The fragments
    themselves are otherwise left as printed, because the card built from them
    breaks where the page broke.
    """
    healed: list[str] = []
    for fragment in fragments:
        if healed and healed[-1].endswith("-"):
            healed[-1] = _rejoined(healed[-1], fragment)
        else:
            healed.append(fragment)
    return healed


def _rejoined(previous: str, following: str) -> str:
    """Two fragments, joined at the word the hyphen sits inside.

    Taking the hyphen out is right for a word the typesetter broke to fit the
    column -- `reg-` and `ulations` are `regulations`. Keeping it is right for a
    hyphen the author typed that happened to land at the break, as `non-` and
    `variable` are `non-variable`. The dictionary decides which, because the two
    are identical on the page.
    """
    broken = previous[previous.rfind(" ") + 1 :]
    tail = _leading_letters(following)
    whole = broken[:-1] + tail
    joined = whole if is_word(whole) else broken + tail
    return previous[: -len(broken)] + joined + following[len(tail) :]


def _leading_letters(text: str) -> str:
    """The run of letters a fragment opens with, which is where a broken word resumes.

    The corpus sometimes loses the space after a word, so `transform-` continues
    into `ers...the Optimus Prime`; only the letters are the rest of the word.
    """
    end = 0
    while end < len(text) and text[end].isalpha():
        end += 1
    return text[:end]


def cell(rows: list[Row], edges: tuple[float, ...], index: int) -> str:
    """One cell of one vocabulary term, its lines joined into a single value."""
    fragments = [
        word.text
        for row in rows
        for word in row.words
        if _column_of(word, edges) == index
    ]
    return " ".join(heal_wrapped_words(fragments))
