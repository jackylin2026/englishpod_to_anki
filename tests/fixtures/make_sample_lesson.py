"""Draw the sample lesson PDF the preprocess tests read.

The corpus itself is copyrighted and is not committed, so the fixture is drawn
from scratch. It is not a copy of any lesson: the words are invented. What it
does copy is the *geometry* of a real lesson PDF, measured from the corpus, so
that the tests exercise the parsing the real files demand:

- three vocabulary columns at x=97, 244 and 354, which differ between the
  corpus's two layout families and so are never hard-coded by the parser
- a term and a part of speech each wrapped over several physical lines
- a term hyphenated across a line break (`immac-` / `ulate`)
- a term split across a line break at a space (`write` / `off`)
- a justified line inside a cell, whose stretched space sits at x=179 and is
  wider than a space but narrower than the gap between two columns -- a parser
  that trusts every wide gap finds four columns here instead of three
- the Key Vocabulary table spanning a page break
- the page footer that appears on every page of the corpus
- a speaker label wide enough to run into the first word the speaker says, so
  the two overlap on the page and ordering by position alone interleaves them
- a contraction printed as two runs of glyphs a shade further apart than a space
- a possessive ending in an apostrophe straight in front of a broken word
- a hyphen the author typed landing at a line break (`entry-level`), next to one
  the typesetter inserted (`immac-` / `ulate`), which only the dictionary can
  tell apart

It also draws a second, image-only lesson for the no-text-layer case.

The two `englishpod_*dg.mp3` files beside those PDFs are a second of silence
made with `ffmpeg -f lavfi -i anullsrc=r=22050:cl=mono -t 1 -b:a 32k`: the build
and import tests need a lesson's dialogue audio to exist, not to say anything.
The Markdown under `markdown_lesson/`, by contrast, is written by hand rather
than drawn -- it is there to put the vocabulary cases the card has to match in
front of the reader, rather than in a PDF.

Run it with `python tests/fixtures/make_sample_lesson.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4
FONT = "Helvetica"

TITLE_X = 89.0
LABEL_X = 95.0
BODY_X = 129.0
TERM_X, POS_X, DEFINITION_X = 97.0, 244.0, 354.0

TITLE_SIZE = 13.0
TERM_SIZE = 11.0
BODY_SIZE = 10.0

LINE_PITCH = 20.0  # between the lines of one entry
ENTRY_PITCH = 60.0  # from one entry to the next
TERM_RISE = 2.0  # the term line sits slightly above its row's other text

# The widest gap a justified line may open inside a cell. Deliberately smaller
# than the 47pt between the term and part-of-speech columns, and smaller than
# the 54pt between the part-of-speech and definition columns.
JUSTIFIED_GAP = 54.0


@dataclass(frozen=True)
class Line:
    """One physical line of a vocabulary table."""

    term: list[str] = field(default_factory=list)
    pos: list[str] = field(default_factory=list)
    definition: list[str] = field(default_factory=list)
    justified: bool = False


@dataclass(frozen=True)
class Entry:
    lines: list[Line]


@dataclass(frozen=True)
class Sample:
    """One lesson as a batch's combined PDF holds it."""

    code: str
    title: str
    dialogue: list[tuple[str, list[str]]]
    key_vocabulary: list[Entry]
    supplementary_vocabulary: list[Entry]
    # Whether the title runs past the column, printing its code beside the
    # second line, as lesson 0259's does in the corpus.
    wrapped_title: bool = False


def word_width(word: str, size: float) -> float:
    return pdfmetrics.stringWidth(word, FONT, size)


def draw_row(pdf: canvas.Canvas, top: float, words: list[str], x: float, size: float,
             gap_after_first: float = 0.0) -> None:
    """Draw a cell's words left to right, one space apart."""
    pdf.setFont(FONT, size)
    for index, word in enumerate(words):
        pdf.drawString(x, PAGE_HEIGHT - top, word)
        x += word_width(word, size) + word_width(" ", size)
        if index == 0:
            x += gap_after_first


def draw_entry(pdf: canvas.Canvas, top: float, entry: Entry) -> None:
    for offset, line in enumerate(entry.lines):
        line_top = top + offset * LINE_PITCH
        gap = JUSTIFIED_GAP if line.justified else 0.0
        draw_row(pdf, line_top - TERM_RISE, line.term, TERM_X, TERM_SIZE, gap)
        draw_row(pdf, line_top, line.pos, POS_X, BODY_SIZE)
        draw_row(pdf, line_top, line.definition, DEFINITION_X, BODY_SIZE)


def draw_line(pdf: canvas.Canvas, top: float, segments: list[tuple[float, str]]) -> None:
    """Draw one physical dialogue line, each segment at its own x."""
    pdf.setFont(FONT, BODY_SIZE)
    for x, text in segments:
        pdf.drawString(x, PAGE_HEIGHT - top, text)


def after(text: str, x: float, gap: float = 0.0) -> float:
    """Where the word following `text`, drawn from `x`, begins."""
    return x + word_width(text, BODY_SIZE) + gap


def draw_footer(pdf: canvas.Canvas) -> None:
    pdf.setFont(FONT, 8.0)
    pdf.drawString(89, PAGE_HEIGHT - 772, "Visit the Online Review and Discussion (text version).")
    pdf.drawString(377, PAGE_HEIGHT - 772, "(c) 2008 Praxis Language Ltd.")


# A label wide enough to run into the first word of what the speaker says, as
# lesson 0152's `Mary:` does. The two overlap on the page, so ordering the line
# by position alone interleaves their letters.
WIDE_LABEL = "Veronica:"

DIALOGUE = [
    (140.0, [(LABEL_X, "A:"), (BODY_X, "Morning, Ed. The auditors arrive on Monday, and I")]),
    (160.0, [(BODY_X, "want the stockroom immac-")]),
    (180.0, [(BODY_X, "ulate before they get here.")]),
    (220.0, [(LABEL_X, "B:"), (BODY_X, "I have been dreading this. Half the pallets are")]),
    (240.0, [(BODY_X, "still unlabelled and the shutter is jammed.")]),
    (280.0, [(LABEL_X, "A:"), (BODY_X, "Then get the labels printed today. Move the")]),
    (300.0, [(BODY_X, "overflow into the annex before the audit.")]),
    (340.0, [(LABEL_X, "B:"), (BODY_X, "And the damaged crates? We cannot simply write")]),
    (360.0, [(BODY_X, "them off without a signature.")]),
    (400.0, [(LABEL_X, WIDE_LABEL), (BODY_X, "I have told you twice already.")]),
    # `You've` printed as two runs of glyphs, a shade further apart than a space.
    (440.0, [(LABEL_X, "A:"), (BODY_X, "You"), (after("You", BODY_X, 5.4), "’ve made your point.")]),
    # A possessive ending in an apostrophe, directly in front of a broken word. Its
    # apostrophe is not an unfinished contraction, so it must not swallow `va-`.
    (480.0, [(LABEL_X, "B:"), (BODY_X, "I have two weeks’ va-")]),
    (500.0, [(BODY_X, "cation left before term starts.")]),
    # The typesetter's break, which goes: `entrylevel` is not a word, but the
    # hyphen here is the author's, so `entry-level` keeps it.
    (540.0, [(LABEL_X, "A:"), (BODY_X, "We only hire at entry-")]),
    (560.0, [(BODY_X, "level for this role.")]),
]

KEY_VOCABULARY = [
    Entry([
        Line(["stockroom"], ["common"], ["the room where goods"]),
        Line([], ["noun,"], ["are kept"]),
        Line([], ["singular"]),
    ]),
    Entry([
        Line(["immaculate"], ["Adjective"], ["perfectly clean"]),
    ]),
    Entry([
        Line(["write"], ["phrasal verb"], ["to cancel a debt"]),
        Line(["off"]),
    ]),
    Entry([
        Line(["open", "mic"], ["common"], ["a slot where anyone"], justified=True),
        Line(["night"], ["noun,"], ["may perform"]),
        Line([], ["singular"]),
    ]),
    Entry([
        Line(["pallet"], ["common"], ["a platform for"]),
        Line([], ["noun,"], ["stacking goods"]),
        Line([], ["singular"]),
    ]),
]

SUPPLEMENTARY_VOCABULARY = [
    Entry([
        Line(["ledger"], ["common"], ["a book of accounts"]),
        Line([], ["noun,"]),
        Line([], ["singular"]),
    ]),
    Entry([
        Line(["dread"], ["verb"], ["to fear something"]),
    ]),
    Entry([
        Line(["crate"], ["common"], ["a wooden box for"]),
        Line([], ["noun,"], ["moving goods"]),
        Line([], ["singular"]),
    ]),
]


def build(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)

    pdf.setFont(FONT, TITLE_SIZE)
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 95, "The Office - Stocktaking")
    pdf.drawString(405.0, PAGE_HEIGHT - 95, "(C0108)")
    for top, segments in DIALOGUE:
        draw_line(pdf, top, segments)
    # The Key Vocabulary table begins on the dialogue's last page and runs on.
    pdf.setFont(FONT, TITLE_SIZE)
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 600, "Key Vocabulary")
    draw_entry(pdf, 640.0, KEY_VOCABULARY[0])
    draw_entry(pdf, 740.0, KEY_VOCABULARY[1])
    draw_footer(pdf)
    pdf.showPage()

    draw_entry(pdf, 95.0, KEY_VOCABULARY[2])
    draw_entry(pdf, 175.0, KEY_VOCABULARY[3])
    draw_entry(pdf, 275.0, KEY_VOCABULARY[4])
    draw_footer(pdf)
    pdf.showPage()

    pdf.setFont(FONT, TITLE_SIZE)
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 60, "Supplementary Vocabulary")
    draw_entry(pdf, 100.0, SUPPLEMENTARY_VOCABULARY[0])
    draw_entry(pdf, 200.0, SUPPLEMENTARY_VOCABULARY[1])
    draw_entry(pdf, 280.0, SUPPLEMENTARY_VOCABULARY[2])
    draw_footer(pdf)
    pdf.showPage()

    pdf.save()


# The x the corpus prints a lesson's code at, on its title's line.
CODE_X = 405.0

# How far down a page the drawing may reach before the next line goes on a new one.
PAGE_BOTTOM = 720.0

SAMPLE_LESSONS = [
    Sample(
        code="C0110",
        title="Around Town - Buying a Bicycle",
        dialogue=[
            ("A", ["Is the bicycle in the window still for sale?"]),
            ("B", ["It is, but the brakes need work."]),
            ("A", ["I can fix the brakes myself. What are you", "asking for it?"]),
            ("B", ["Sixty, and the saddle is new."]),
        ],
        key_vocabulary=[
            Entry([Line(["bicycle"], ["common noun"], ["a two-wheeled machine"]),
                   Line([], [], ["to ride"])]),
            Entry([Line(["brakes"], ["common noun"], ["the parts that stop"]),
                   Line([], [], ["a wheel"])]),
        ],
        supplementary_vocabulary=[
            Entry([Line(["saddle"], ["common noun"], ["the seat of a bicycle"])]),
        ],
    ),
    Sample(
        code="C0111",
        # A title long enough to wrap, the way 0256's and 0259's do: the code
        # prints beside the second line, which is where the lesson begins.
        title="Daily Life - Fixing the Kettle",
        wrapped_title=True,
        dialogue=[
            ("A", ["The kettle has stopped working again."]),
            ("B", ["Did you descale it?"]),
            ("A", ["I did, and it still will not boil."]),
        ],
        key_vocabulary=[
            Entry([Line(["kettle"], ["common noun"], ["a pot for boiling water"])]),
            Entry([Line(["descale"], ["verb"], ["to take the mineral"]),
                   Line([], [], ["deposit off"])]),
        ],
        supplementary_vocabulary=[
            Entry([Line(["boil"], ["verb"], ["to heat a liquid until"]),
                   Line([], [], ["it bubbles"])]),
        ],
    ),
]


def draw_sample(pdf: canvas.Canvas, top: float, sample: Sample) -> float:
    """Draw one lesson, and answer where the next thing may be drawn.

    A lesson in a batch's PDF looks like a lesson PDF's worth of content with no
    page of its own: its title, its dialogue, and its two tables, drawn one
    after another on the page the last lesson left off on.
    """
    pdf.setFont(FONT, TITLE_SIZE)
    if sample.wrapped_title:
        first, rest = sample.title.split(" - ", 1)
        pdf.drawString(TITLE_X, PAGE_HEIGHT - top, first + " -")
        top += LINE_PITCH
        pdf.drawString(TITLE_X, PAGE_HEIGHT - top, rest)
        pdf.drawString(CODE_X, PAGE_HEIGHT - top, f"({sample.code})")
    else:
        pdf.drawString(TITLE_X, PAGE_HEIGHT - top, sample.title)
        pdf.drawString(CODE_X, PAGE_HEIGHT - top, f"({sample.code})")
    top += LINE_PITCH * 2

    for label, lines in sample.dialogue:
        for index, text in enumerate(lines):
            segments = [(LABEL_X, f"{label}:")] if index == 0 else []
            draw_line(pdf, top, [*segments, (BODY_X, text)])
            top += LINE_PITCH
        top += LINE_PITCH / 2
    top += LINE_PITCH * 3

    for heading, entries in (
        ("Key Vocabulary", sample.key_vocabulary),
        ("Supplementary Vocabulary", sample.supplementary_vocabulary),
    ):
        pdf.setFont(FONT, TITLE_SIZE)
        pdf.drawString(TITLE_X, PAGE_HEIGHT - top, heading)
        top += LINE_PITCH * 2
        for entry in entries:
            draw_entry(pdf, top, entry)
            top += ENTRY_PITCH * 0.6 + LINE_PITCH * (len(entry.lines) - 1)
        top += LINE_PITCH * 2
    return top


def build_batch(path: Path, samples: list[Sample]) -> None:
    """Draw several lessons into one PDF, as the corpus's batches keep them.

    Nothing marks where one lesson ends and the next begins except the row each
    title prints its code on, and a lesson does not begin on a page of its own:
    the drawing breaks the page only when it would otherwise run off the bottom.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    top = 120.0
    for sample in samples:
        if top > PAGE_BOTTOM:
            draw_footer(pdf)
            pdf.showPage()
            top = 120.0
        top = draw_sample(pdf, top, sample)
    draw_footer(pdf)
    pdf.save()


def build_intro(path: Path, number: str, title: str) -> None:
    """Draw the introduction sheet the corpus keeps in place of a lesson PDF.

    It names the lesson and says what it is about. It carries no lesson code,
    no dialogue and no vocabulary, which is why a lesson holding one has to be
    read out of the PDF beside it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont(FONT, TITLE_SIZE)
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 95, "EnglishPod Lesson Introduction")
    pdf.setFont(FONT, BODY_SIZE)
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 130, f"{number} {title}")
    pdf.drawString(TITLE_X, PAGE_HEIGHT - 160, "Today we discuss " + title.lower() + ".")
    draw_footer(pdf)
    pdf.save()


def build_scanned(path: Path) -> None:
    """Draw a lesson that is only a picture, with no text layer whatsoever.

    Around seventy lessons in the corpus are image-only scans. Preprocess cannot
    read them and must say so rather than write an empty Markdown file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFillColorRGB(0.86, 0.86, 0.86)
    pdf.rect(89.0, PAGE_HEIGHT - 420, 420.0, 300.0, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0.35, 0.35, 0.35)
    for step in range(12):
        indent = 110.0 + step * 6
        pdf.line(indent, PAGE_HEIGHT - 400 + step * 22, 470.0 - step * 9, PAGE_HEIGHT - 400 + step * 22)
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    build(destination / "lesson" / "englishpod_D0108.pdf")
    build_scanned(destination / "scanned_lesson" / "englishpod_C0109.pdf")
    batch = destination / "corpus" / "0110-0111"
    build_batch(batch / "0110-0111.pdf", SAMPLE_LESSONS)
    build_intro(batch / "0110" / "EnglishPod.Intro.0110.pdf", "0110", "Around Town - Buying a Bicycle")
    build_intro(batch / "0111" / "EnglishPod.Intro.0111.pdf", "0111", "Daily Life - Fixing the Kettle")
    for written in (
        destination / "lesson" / "englishpod_D0108.pdf",
        destination / "scanned_lesson" / "englishpod_C0109.pdf",
        batch / "0110-0111.pdf",
        batch / "0110" / "EnglishPod.Intro.0110.pdf",
        batch / "0111" / "EnglishPod.Intro.0111.pdf",
    ):
        print(f"wrote {written}")
