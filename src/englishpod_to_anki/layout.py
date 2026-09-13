"""Recovering the physical layout of a PDF.

A lesson PDF holds one column of dialogue followed by two three-column
vocabulary tables; the corpus's print transcript holds two columns of dialogue
to a page. Nothing in either file marks where a column begins, so the geometry is
recovered from where the words sit on the page.

Reading the words back out is part of the same job: the page breaks words and
prints contractions as several runs of glyphs, and putting them back together
needs to know where the columns end and what the words are.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
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

# How near two words have to sit to be read as printed at the same column's
# edge. A column is set once and prints at one x every time it is asked to: the
# corpus's label columns agree to the tenth of a point across a dialogue. A page
# read back off its own picture is a service's estimate of where a word was, and
# a reading that disagrees with itself by more than this is read as it stands.
COLUMN_TOLERANCE = 0.5

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
    """One word of a row: what it says, where it sits, and the size it is set in.

    The size is what a document says about a word without words -- a heading is
    set larger than the dialogue under it -- and is absent when the reading has
    none to give, as a page read back off its own picture by the OCR pass has.
    """

    text: str
    x0: float
    x1: float
    size: float | None = None


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
    size: float | None = None


@dataclass(frozen=True)
class Row:
    """One physical line of a page."""

    page: int
    top: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        """The row's words, in reading order."""
        return _text(self.words)

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
    """Every physical line of a one-column PDF in reading order, footers dropped."""
    rows: list[Row] = []
    for number, words in _pages(path):
        rows += page_rows(number, words)
    return rows


def read_columns(path: Path) -> list[Row]:
    """Every physical line of a PDF printed in columns, in reading order.

    A page printed in columns is not read the way a page of one column is: a line
    belongs to the column it sits in rather than to the row it shares a height
    with, so the words are split into the page's columns first and each column is
    read top to bottom, the columns left to right, page by page.

    The page's own number is printed at the foot of the page, in the gutter
    between the columns. It belongs to the page rather than to what is printed in
    the columns, and reading it as one of them would cut the gutter in two and
    take the page's columns with it.
    """
    rows: list[Row] = []
    for number, words in _pages(path, sizes=True):
        lines = _without_the_page_number(_by_top(words))
        for column in _columns(lines):
            rows += page_rows(number, column)
    return rows


def _pages(path: Path, *, sizes: bool = False) -> Iterator[tuple[int, list[Seen]]]:
    """Every page's words in order, whichever way the caller reads lines off them.

    A file that is not a PDF this can open -- truncated, or not a PDF at all --
    is the lesson's problem rather than the run's, so it is reported the way
    every other unreadable lesson is: a run over a corpus skips that lesson and
    carries on, and a stage pointed at it says what is wrong rather than letting
    the library's error out as a traceback.
    """
    try:
        with pdfplumber.open(path) as pdf:
            for number, page in enumerate(pdf.pages):
                yield number, _page_words(page, sizes=sizes)
    except (OSError, PdfminerException) as error:
        raise LessonError(f"cannot read {path}: {error}") from error


def _page_words(page: pdfplumber.page.Page, *, sizes: bool = False) -> list[Seen]:
    """A page's words, as the kind of reading every way of reading lines works in."""
    return [
        Seen(
            text=word["text"],
            top=word["top"],
            x0=word["x0"],
            x1=word["x1"],
            size=word.get("size"),
        )
        for word in _words(page, sizes=sizes)
    ]


def _without_the_page_number(lines: list[list[Seen]]) -> list[list[Seen]]:
    """A page's lines with its own number taken off the foot, if it carries one."""
    if lines and " ".join(word.text for word in lines[-1]).strip().isdigit():
        return lines[:-1]
    return lines


def _columns(lines: list[list[Seen]]) -> list[list[Seen]]:
    """A page's lines as its columns' words, left to right.

    A page whose lines stand in one column answers with them all at once, which
    is what makes a document that is not printed in columns readable this way
    too.
    """
    edges = _column_edges((word.x0, word.x1) for line in lines for word in line)
    return [
        [word for line in lines for word in line if _column_of(word.x0, edges) == index]
        for index in range(len(edges))
    ]


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
                _rejoin_apostrophes(
                    [Word(word.text, word.x0, word.x1, word.size) for word in line]
                )
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
            rejoined[-1] = Word(last.text + word.text, last.x0, word.x1, last.size)
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


def _words(page: pdfplumber.page.Page, *, sizes: bool = False) -> list[dict[str, Any]]:
    """A page's words, grouped as the PDF itself laid them out.

    Reading the flow rather than the page geometry keeps a wide speaker label
    whole on the lessons where it overlaps the first word of what that speaker
    says. Both are drawn over each other, and ordering by position alone
    interleaves their letters.

    A word's size is how a document that sets its headings larger than its body
    says which lines are which, and it is asked for only where it is wanted: a
    page's words are grouped by the attributes they are asked for, so asking for
    a lesson's sizes reads the lesson's lines differently -- measured on the
    corpus, on every page of one of its lessons.
    """
    return page.extract_words(
        use_text_flow=True, extra_attrs=["size"] if sizes else None
    )


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
    """The left edge of each column of a vocabulary table."""
    return _column_edges((word.x0, word.x1) for row in rows for word in row.words)


def _column_edges(spans: Iterable[tuple[float, float]]) -> tuple[float, ...]:
    """The left edge of each column the given words stand in.

    The two widest gaps that stay empty down the whole of them separate the
    columns. Narrower empty gaps are the stretched spaces of a justified line
    inside a cell, which can be wider than a column's own margin.
    """
    spans = sorted(spans)
    if not spans:
        return ()
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


def _column_of(x0: float, edges: tuple[float, ...]) -> int:
    """Which column the word starting here falls in, given the columns' left edges."""
    index = 0
    for position, edge in enumerate(edges):
        if x0 >= edge - 0.5:
            index = position
    return index


# One row of a dialogue as the label printed at its head and the body beside it.
Labelled = tuple[str, str]


def labelled_rows(rows: Sequence[Row]) -> list[Labelled]:
    """A dialogue's rows, each as the label printed at its head and the body beside it.

    A label the column the corpus prints labels in is too narrow for takes two
    rows: the label's first half ends the row and the body begins after it, and
    the label's second half opens the next row before the body carries on. Read
    as the rows stand, the halves fall on either side of the body's first words,
    and a word the typesetter broke at the row's end is healed against the wrong
    fragment -- `Older gentle-` and `man:` come back as two words that are not
    the label either of them is half of.

    Only the rows a two-row label is printed over are read any differently. A
    label the column fits on one row is left where it is, and so is every row
    that carries no label at all: those answer with the row's own text and no
    label, which is what the caller reads a row as until a label says otherwise.
    """
    body_at = _body_column(rows)
    if body_at is None:
        return [("", row.text) for row in rows]

    labelled: list[Labelled] = []
    index = 0
    while index < len(rows):
        split = _two_row_label(rows, index, body_at)
        if split is None:
            labelled.append(("", rows[index].text))
            index += 1
            continue
        label, first, second = split
        labelled.append((label, first))
        labelled.append(("", second))
        index += 2
    return labelled


def _two_row_label(rows: Sequence[Row], index: int, body_at: float) -> tuple[str, str, str] | None:
    """The label printed over two rows beginning at `index`, and each row's body.

    The label's second half is what says a label is printed here: it is the word
    carrying the colon the label ends at. What is above it is read off that row's
    own words -- the ones printed at the label's column, which is the column the
    row below prints its half of the label at -- and the two halves are a label's
    two halves rather than two rows' openings only if they join into one: a colon
    after one or two words, healable at the break the way any broken word is.

    Two rows are all this reads, and a label printed over three -- lesson 0119's
    `Scruffy puffy poo:` is, with the body beginning beside its first word -- is
    left as the rows stand: a row with a half of a label above it is not the row
    a label begins on, so no pair of these two is the whole of that label.
    """
    if index + 1 >= len(rows):
        return None
    first, second = rows[index], rows[index + 1]
    tail = _to_the_colon(second.words)
    if not tail:
        return None
    # The row above carries the label's first half only if it carries a half at
    # all: words of its own at the label's column, and none of them a label's
    # end -- a half with a colon in it is a label already, and the row below is
    # a new speaker rather than the rest of that one.
    half = _left_of(first.words, body_at)
    if not half or any(":" in word.text for word in half):
        return None
    # The row above carries nothing more of this label, or carries a label of
    # its own: a row whose words sit at this label's column but do not end at a
    # colon is a half of a label the column broke over three rows, and no pair
    # of rows here is the whole of it.
    if index:
        above = _at_column(rows[index - 1].words, half[0].x0)
        if above and not any(":" in word.text for word in above):
            return None
    # The two halves are printed at the one column, the label's: a body word
    # beginning where the label's second half does is the row's own body.
    if abs(half[0].x0 - tail[0].x0) > COLUMN_TOLERANCE:
        return None
    # A label's first half ends the row the body of what the speaker says begins
    # on, and a dialogue printed in two columns indents every body to the one
    # place: the words after the half are the body's, and they begin where the
    # body beside the label does. A row whose next word stands somewhere else --
    # or whose half is the whole of the row -- is a row of body rather than the
    # row a label begins on, and is left to the body it belongs to.
    rests = first.words[len(half) :]
    if not rests or abs(rests[0].x0 - body_at) > COLUMN_TOLERANCE:
        return None
    label = " ".join(heal_wrapped_words([_text(half), _text(tail)]))
    if len(label.split()) not in (1, 2) or not label.endswith(":"):
        return None
    return label, _text(rests), _text(second.words[len(tail) :])


def _to_the_colon(words: Sequence[Word]) -> tuple[Word, ...]:
    """A row's leading words up to and including the first one carrying a colon.

    A label ends at its colon, so this is what a row carries of one: the whole
    label where the column fitted it on the row, and the label's last half where
    it did not. A row carrying no colon carries no part of a label.
    """
    for index, word in enumerate(words):
        if ":" in word.text:
            return tuple(words[: index + 1])
    return ()


def _left_of(words: Sequence[Word], column: float) -> tuple[Word, ...]:
    """A row's leading words printed left of the column the body begins at."""
    end = 0
    while end < len(words) and words[end].x0 < column - COLUMN_TOLERANCE:
        end += 1
    return tuple(words[:end])


def _at_column(words: Sequence[Word], column: float) -> tuple[Word, ...]:
    """A row's leading words printed at one column's edge."""
    end = 0
    while end < len(words) and abs(words[end].x0 - column) <= COLUMN_TOLERANCE:
        end += 1
    return tuple(words[:end])


def _body_column(rows: Sequence[Row]) -> float | None:
    """The x a dialogue's bodies begin at, where they all begin at one.

    A label ends at its colon, so the body beside it begins at the word after
    it, and a label the column broke over two rows says as much from the row it
    ends on as any label does. Every row of a dialogue printed in two columns is
    a label or a body of one, so its bodies all begin at the one x: measured on
    the corpus, every dialogue of it that prints a body beside a label prints
    all of them at a single x.

    A dialogue that begins its bodies wherever its labels end has no second
    column at all, and answers with nothing: the print transcript prints every
    body against its own label, and no label of it is printed over two rows, so
    nothing is read differently there.
    """
    begins = [
        row.words[1].x0
        for row in rows
        if len(row.words) > 1 and row.words[0].text.endswith(":")
    ]
    if not begins or any(abs(x - begins[0]) > COLUMN_TOLERANCE for x in begins):
        return None
    return begins[0]


def _text(words: Sequence[Word]) -> str:
    """A run of words, in reading order."""
    return " ".join(word.text for word in words)


def term_rows(rows: list[Row]) -> list[list[Row]]:
    """Split a vocabulary table's rows into one group per vocabulary term.

    A term's own lines sit close together and the gap before the next term is
    wider. The pitch is the narrowest gap between two rows -- but a gap too
    narrow to be one is not a pitch: a table read back off a picture has a row
    whose two boxes sit a fraction of a point apart, and reading that off as the
    table's pitch made every row a term of its own, filling the tables of a
    third of the corpus's scans with empty-term rows. A page break always begins
    a new term.

    Where nothing is set wider than anything else, there is no narrower gap to
    take a pitch from: the narrowest is the gap between terms rather than a
    term's own leading, and reading it as one puts the whole table into a single
    term. A page prints a term's lines closer than the gap before its next term
    -- that difference is what this reads, and a table without it is set one row
    to a term.
    """
    if not rows:
        return []
    pitches = [
        following.top - current.top
        for current, following in zip(rows, rows[1:])
        if current.page == following.page and following.top > current.top
    ]
    pitches = [pitch for pitch in pitches if pitch >= NARROWER_THAN_A_ROW] or pitches
    if pitches and max(pitches) < min(pitches) * TERM_GAP_FACTOR:
        pitches = []
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
        if _column_of(word.x0, edges) == index
    ]
    return " ".join(heal_wrapped_words(fragments))
