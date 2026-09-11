"""Recovering the physical layout of a lesson PDF.

A lesson PDF holds one column of dialogue followed by two three-column
vocabulary tables. Nothing in the file marks where a column begins, so the
geometry is recovered from where the words sit on the page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pdfplumber

# Words whose tops are closer together than this sit on the same physical line.
ROW_TOLERANCE = 6.0

# A horizontal gap narrower than this is the space between two words, not
# between two columns.
MIN_GUTTER = 8.0

# A vertical gap this many times the table's tightest row pitch begins a new term.
TERM_GAP_FACTOR = 1.5

# What an English contraction can end in once its apostrophe is taken off:
# I'm, you've, he's, don't, we'd, they'll, you're. Anything longer is a word in
# its own right that happens to open with an apostrophe.
CONTRACTION_TAILS = frozenset({"m", "s", "t", "d", "ll", "re", "ve"})

# Printed at the foot of every page of the corpus and belonging to no lesson.
FOOTER = re.compile(
    r"Visit.*OnlineReview.*Discussion.*textversion|PraxisLanguageLtd",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Word:
    text: str
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
        """The row's words with no spaces, for matching a phrase that may be split."""
        return "".join(word.text for word in self.words)


def read_rows(path: Path) -> list[Row]:
    """Every physical line of the PDF in reading order, page footers dropped."""
    rows: list[Row] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages):
            for line in _lines(_words(page)):
                row = Row(
                    page=number,
                    top=max(word["top"] for word in line),
                    words=tuple(
                        _rejoin_apostrophes(
                            [Word(word["text"], word["x0"], word["x1"]) for word in line]
                        )
                    ),
                )
                if not FOOTER.search(row.squashed):
                    rows.append(row)
    return rows


def _rejoin_apostrophes(words: list[Word]) -> list[Word]:
    """Put back together a word the PDF printed as more than one run of glyphs.

    Contractions arrive in two broken shapes. The apostrophe can be a run of its
    own, so `I'll` comes as `I`, `'`, `ll`. Or it can be glued to what follows
    it, so `You've` comes as `You` and `'ve`.
    """
    rejoined: list[Word] = []
    for word in words:
        if rejoined and _belongs_to_previous(word, rejoined[-1]):
            last = rejoined[-1]
            rejoined[-1] = Word(last.text + word.text, last.x0, word.x1)
        else:
            rejoined.append(word)
    return rejoined


def _belongs_to_previous(word: Word, previous: Word) -> bool:
    if _is_stray_apostrophe(word) or _ends_on_stray_apostrophe(previous):
        return True
    # Only a contraction's tail is glued back on, so a word that really does open
    # with an apostrophe -- `'tis`, `'bout` -- keeps the space in front of it.
    tail = word.text.removeprefix("'").removeprefix("’")
    return (
        tail != word.text
        and tail.isalpha()
        and tail.lower() in CONTRACTION_TAILS
        and previous.text[-1:].isalpha()
    )


def _is_stray_apostrophe(word: Word) -> bool:
    return word.text != "" and word.text.strip("'’") == ""


def _ends_on_stray_apostrophe(word: Word) -> bool:
    """Whether this fragment is an apostrophe already joined to a word, with nothing after it.

    Requiring more than one character keeps a quotation mark that opens a line
    from swallowing the word that follows it.
    """
    return len(word.text) > 1 and word.text[-1] in "'’"


def _words(page: pdfplumber.page.Page) -> list[dict[str, Any]]:
    """A page's words, grouped as the PDF itself laid them out.

    Reading the flow rather than the page geometry keeps a wide speaker label
    whole on the lessons where it overlaps the first word of what that speaker
    says. Both are drawn over each other, and ordering by position alone
    interleaves their letters.
    """
    return page.extract_words(use_text_flow=True)


def _lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group a page's words into physical lines, left to right."""
    if not words:
        return []
    ordered = sorted(words, key=lambda word: (word["top"], word["x0"]))
    lines = [[ordered[0]]]
    for word in ordered[1:]:
        if word["top"] - lines[-1][0]["top"] <= ROW_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda word: word["x0"]) for line in lines]


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
    wider. A page break always begins a new term.
    """
    if not rows:
        return []
    pitches = [
        following.top - current.top
        for current, following in zip(rows, rows[1:])
        if current.page == following.page and following.top > current.top
    ]
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

    A fragment ending in a hyphen is a word split by a line break, so the hyphen
    goes and the halves close up. The fragments themselves are otherwise left as
    printed, because the card built from them breaks where the page broke.
    """
    healed: list[str] = []
    for fragment in fragments:
        if healed and healed[-1].endswith("-"):
            healed[-1] = healed[-1][:-1] + fragment
        else:
            healed.append(fragment)
    return healed


def cell(rows: list[Row], edges: tuple[float, ...], index: int) -> str:
    """One cell of one vocabulary term, its lines joined into a single value."""
    fragments = [
        word.text
        for row in rows
        for word in row.words
        if _column_of(word, edges) == index
    ]
    return " ".join(heal_wrapped_words(fragments))
