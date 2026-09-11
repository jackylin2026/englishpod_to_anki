"""Preprocess, tested the only way the spec allows: through the command line.

Every test runs the tool as a subprocess against the sample lesson directory and
asserts on the Markdown it wrote, never on the tool's internals. The sample
lesson is drawn by `tests/fixtures/make_sample_lesson.py`.

The sample lesson's file is named for lesson D0108 while the code printed inside
it reads C0108, which is the disagreement the corpus really has.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import BATCH
from stub_ocr import StubOcr

MARKDOWN = "englishpod_D0108.md"

EXPECTED_DIALOGUE = """\
A: Morning, Ed. The auditors arrive on Monday, and I
want the stockroom immaculate before they get here.

B: I have been dreading this. Half the pallets are
still unlabelled and the shutter is jammed.

A: Then get the labels printed today. Move the
overflow into the annex before the audit.

B: And the damaged crates? We cannot simply write
them off without a signature.

Veronica: I have told you twice already.

A: You’ve made your point.

B: I have two weeks’ vacation left before term starts.

A: We only hire at entry-level for this role."""

EXPECTED_KEY_VOCABULARY = [
    ("stockroom", "common noun, singular", "the room where goods are kept"),
    ("immaculate", "Adjective", "perfectly clean"),
    ("write off", "phrasal verb", "to cancel a debt"),
    ("open mic night", "common noun, singular", "a slot where anyone may perform"),
    ("pallet", "common noun, singular", "a platform for stacking goods"),
]

EXPECTED_SUPPLEMENTARY_VOCABULARY = [
    ("ledger", "common noun, singular", "a book of accounts"),
    ("dread", "verb", "to fear something"),
    ("crate", "common noun, singular", "a wooden box for moving goods"),
]


def preprocessed(lesson: Path, run_cli, *arguments: object) -> str:
    """Run preprocess over the sample lesson and return the Markdown it wrote."""
    result = run_cli("preprocess", lesson, *arguments)
    assert result.returncode == 0, result.stderr
    return (lesson / MARKDOWN).read_text(encoding="utf-8")


def section(markdown: str, heading: str) -> str:
    """The text under one `## heading`, without the heading."""
    after = markdown.split(f"## {heading}\n", 1)[1]
    return after.split("\n## ", 1)[0].strip("\n")


def table(text: str) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    """A Markdown table's header row and its data rows."""
    rows = [line for line in text.splitlines() if line.startswith("|")]
    cells = [tuple(cell.strip() for cell in row.strip("|").split("|")) for row in rows]
    return cells[0], cells[2:]


def test_writes_a_markdown_file_beside_the_lesson_pdf(lesson: Path, run_cli) -> None:
    preprocessed(lesson, run_cli)

    assert (lesson / MARKDOWN).is_file()
    # The lesson directory holds its PDF, its recordings and now its Markdown --
    # the one file the run adds.
    assert sorted(path.name for path in lesson.iterdir()) == [
        "englishpod_D0108.md",
        "englishpod_D0108.pdf",
        "englishpod_D0108dg.mp3",
    ]


def test_title_carries_the_code_printed_inside_the_pdf(lesson: Path, run_cli) -> None:
    markdown = preprocessed(lesson, run_cli)

    assert markdown.splitlines()[0] == "# C0108"
    # The code is not the one the filename suggests.
    assert "D0108" in (lesson / "englishpod_D0108.pdf").name


def test_dialogue_keeps_its_speaker_labels_and_line_structure(lesson: Path, run_cli) -> None:
    markdown = preprocessed(lesson, run_cli)

    assert section(markdown, "Dialogue") == EXPECTED_DIALOGUE


def test_key_and_supplementary_vocabulary_are_separate_tables(lesson: Path, run_cli) -> None:
    markdown = preprocessed(lesson, run_cli)

    key_header, key_rows = table(section(markdown, "Key Vocabulary"))
    supplementary_header, supplementary_rows = table(
        section(markdown, "Supplementary Vocabulary")
    )

    assert key_header == ("Term", "Part of speech", "Definition")
    assert supplementary_header == ("Term", "Part of speech", "Definition")
    assert key_rows == EXPECTED_KEY_VOCABULARY
    assert supplementary_rows == EXPECTED_SUPPLEMENTARY_VOCABULARY


def test_a_term_split_across_physical_lines_is_reassembled(lesson: Path, run_cli) -> None:
    markdown = preprocessed(lesson, run_cli)
    _, key_rows = table(section(markdown, "Key Vocabulary"))
    _, supplementary_rows = table(section(markdown, "Supplementary Vocabulary"))
    terms = [row[0] for row in key_rows + supplementary_rows]

    # Split over two lines, with the hyphen the typesetter added.
    assert "immaculate" in terms
    # Split over two lines at a space.
    assert "write off" in terms
    # Spread across a justified line inside the cell.
    assert "open mic night" in terms
    # A part of speech wrapped over three lines comes back whole, too.
    assert ("stockroom", "common noun, singular", "the room where goods are kept") in key_rows


def test_a_wide_speaker_label_keeps_the_first_word_it_overlaps(lesson: Path, run_cli) -> None:
    """`Veronica:` overruns the word after it, as lesson 0152's `Mary:` does."""
    dialogue = section(preprocessed(lesson, run_cli), "Dialogue")

    assert "Veronica: I have told you twice already." in dialogue


def test_a_contraction_printed_as_two_runs_is_rejoined(lesson: Path, run_cli) -> None:
    dialogue = section(preprocessed(lesson, run_cli), "Dialogue")

    assert "A: You’ve made your point." in dialogue
    assert " ’" not in dialogue


def test_a_word_the_typesetter_broke_loses_its_hyphen(lesson: Path, run_cli) -> None:
    """`immac-` and `ulate` are `immaculate`; the dictionary knows the whole word."""
    dialogue = section(preprocessed(lesson, run_cli), "Dialogue")

    assert "the stockroom immaculate before" in dialogue
    assert "immac-" not in dialogue
    assert "weeks’ vacation left" in dialogue


def test_a_hyphen_the_author_typed_is_kept(lesson: Path, run_cli) -> None:
    """`entrylevel` is not a word, so the hyphen in `entry-level` is the author's."""
    dialogue = section(preprocessed(lesson, run_cli), "Dialogue")

    assert "hire at entry-level for this role" in dialogue


def test_a_possessive_apostrophe_does_not_swallow_the_next_word(lesson: Path, run_cli) -> None:
    """`weeks’` ends in an apostrophe but is finished; it is not a cut contraction."""
    dialogue = section(preprocessed(lesson, run_cli), "Dialogue")

    assert "two weeks’ vacation" in dialogue
    assert "weeks’v" not in dialogue


def test_a_lesson_pdf_with_no_text_layer_is_reported(scanned_lesson: Path, run_cli) -> None:
    result = run_cli("preprocess", scanned_lesson)

    assert result.returncode == 1
    assert "no text layer" in result.stderr
    assert not (scanned_lesson / "englishpod_C0109.md").exists()


def test_an_existing_markdown_file_is_left_untouched_and_reported(
    lesson: Path, run_cli
) -> None:
    hand_corrected = lesson / MARKDOWN
    hand_corrected.write_text("# C0108\n\nmy own correction\n", encoding="utf-8")

    result = run_cli("preprocess", lesson)

    assert result.returncode == 0
    assert hand_corrected.read_text(encoding="utf-8") == "# C0108\n\nmy own correction\n"
    assert MARKDOWN in result.stdout
    assert "already exists" in result.stdout


def test_force_regenerates_an_existing_markdown_file(lesson: Path, run_cli) -> None:
    (lesson / MARKDOWN).write_text("# C0108\n\nmy own correction\n", encoding="utf-8")

    markdown = preprocessed(lesson, run_cli, "--force")

    assert markdown.startswith("# C0108\n")
    assert "my own correction" not in markdown


def test_a_directory_holding_no_pdf_is_reported(tmp_path: Path, run_cli) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = run_cli("preprocess", empty)

    assert result.returncode == 1
    assert "no PDF" in result.stderr


def test_a_pdf_that_cannot_be_read_is_reported(tmp_path: Path, run_cli) -> None:
    """A truncated or corrupt file is the lesson's problem, not a traceback."""
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    (lesson / "englishpod_D0108.pdf").write_bytes(b"not a PDF at all")

    result = run_cli("preprocess", lesson)

    assert result.returncode == 1
    assert "cannot read" in result.stderr
    assert "englishpod_D0108.pdf" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_lesson_holding_an_introduction_sheet_is_read_from_the_pdf_beside_it(
    corpus: Path, run_cli
) -> None:
    """Above 250 the corpus keeps an introduction sheet where a lesson PDF goes.

    The lesson itself is in the batch's PDF one directory up: a document holding
    ten of them, each beginning at the row that prints its code. The Markdown the
    stage writes lands in the lesson's own directory, named for the code it read.
    """
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()

    result = run_cli("preprocess", lesson)

    assert result.returncode == 0, result.stderr
    written = lesson / "englishpod_C0110.md"
    assert written.is_file()
    markdown = written.read_text(encoding="utf-8")
    assert markdown.startswith("# C0110\n")
    assert "A: Is the bicycle in the window still for sale?" in markdown
    assert "| bicycle | common noun | a two-wheeled machine to ride |" in markdown
    assert "| brakes | common noun | the parts that stop a wheel |" in markdown
    assert "| saddle | common noun | the seat of a bicycle |" in markdown


def test_a_title_printed_over_two_lines_does_not_leak_into_the_lesson_before(
    corpus: Path, run_cli
) -> None:
    """A lesson begins at its title, not at the line carrying its code.

    The second lesson of the fixture's batch prints a title too long for its
    column, so its code sits beside the title's second line -- and the line above
    that belongs to this lesson, not to the one before it. Left in the wrong
    slice, a title line spans the vocabulary table's columns and takes them with
    it: the lesson before would come out with one column instead of three.
    """
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()
    assert run_cli("preprocess", lesson).returncode == 0
    markdown = (lesson / "englishpod_C0110.md").read_text(encoding="utf-8")

    supplementary = section(markdown, "Supplementary Vocabulary")
    rows = [line for line in supplementary.splitlines() if line.startswith("|")]
    # The header, the rule, and the lesson's one entry -- and not the line of
    # the next lesson's title that a slice taken at the code row would swallow.
    assert len(rows) == 3
    assert "| saddle | common noun | the seat of a bicycle |" in supplementary
    assert "Daily Life" not in markdown


def test_force_regenerates_in_place_rather_than_beside_a_renamed_markdown(
    lesson: Path, run_cli
) -> None:
    """A lesson directory holds one Markdown, whatever its owner called it."""
    corrected = lesson / "my-own-notes.md"
    corrected.write_text("# C0108\n\nmy own correction\n", encoding="utf-8")

    result = run_cli("preprocess", lesson, "--force")

    assert result.returncode == 0, result.stderr
    assert corrected.read_text(encoding="utf-8").startswith("# C0108\n")
    assert "my own correction" not in corrected.read_text(encoding="utf-8")
    assert not (lesson / MARKDOWN).exists()


def test_a_scanned_pdf_is_not_looked_for_beside_the_lesson(
    corpus: Path, run_cli, scanned_lesson: Path
) -> None:
    """A scan wants the OCR pass, and is not sent looking for another source.

    Only a lesson code the PDF does not carry sends the stage to the batch's
    PDF; a page of pictures is a different problem with a different answer.
    """
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()
    shutil.copy(scanned_lesson / "englishpod_C0109.pdf", lesson / "englishpod_C0110.pdf")
    (lesson / "EnglishPod.Intro.0110.pdf").unlink()

    result = run_cli("preprocess", lesson)

    assert result.returncode == 1
    assert "has no text layer" in result.stderr
    assert not list(lesson.glob("*.md"))


def test_an_unreadable_pdf_beside_the_lesson_is_passed_over(
    corpus: Path, run_cli
) -> None:
    """One file in the batch that cannot be read must not cost the lesson.

    The lesson's own PDF carries no code, and the first PDF in the batch
    directory -- by name -- is not readable at all: the one carrying the lesson
    is further down the list.
    """
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()
    (corpus / BATCH / "0077 - broken.pdf").write_bytes(b"not a PDF at all")

    result = run_cli("preprocess", lesson)

    assert result.returncode == 0, result.stderr
    assert (lesson / "englishpod_C0110.md").is_file()


def test_a_lesson_is_read_from_whichever_pdf_beside_it_carries_it(
    corpus: Path, run_cli
) -> None:
    """A batch may keep a per-lesson PDF as well as the one holding all of them."""
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()
    shutil.copy(corpus / BATCH / "0110-0111.pdf", corpus / BATCH / "aaa-first.pdf")

    result = run_cli("preprocess", lesson)

    assert result.returncode == 0, result.stderr
    written = lesson / "englishpod_C0110.md"
    assert written.is_file()
    assert "A: Is the bicycle in the window still for sale?" in written.read_text(
        encoding="utf-8"
    )


def test_force_keeps_the_name_a_recovered_lessons_markdown_already_has(
    corpus: Path, run_cli
) -> None:
    """A lesson read from the batch writes to the Markdown it already holds."""
    lesson = corpus / BATCH / "0110"
    (lesson / "englishpod_B0110.md").unlink()
    corrected = lesson / "my-own-notes.md"
    corrected.write_text("# C0110\n\nmy own correction\n", encoding="utf-8")

    result = run_cli("preprocess", lesson, "--force")

    assert result.returncode == 0, result.stderr
    assert corrected.read_text(encoding="utf-8").startswith("# C0110\n")
    assert "my own correction" not in corrected.read_text(encoding="utf-8")
    assert not (lesson / "englishpod_C0110.md").exists()


def test_a_directory_not_named_by_a_number_is_reported_as_it_was(
    corpus: Path, run_cli
) -> None:
    """The fallback needs a number to look for; without one, nothing changes."""
    lesson = corpus / BATCH / "extras"
    shutil.copytree(corpus / BATCH / "0110", lesson)
    (lesson / "englishpod_B0110.md").unlink()

    result = run_cli("preprocess", lesson)

    assert result.returncode == 1
    assert "carries no lesson code" in result.stderr
    assert not list(lesson.glob("*.md"))


def test_a_lesson_no_pdf_beside_it_carries_is_reported(corpus: Path, run_cli) -> None:
    """The lesson is looked for beside it, by the number its directory is named.

    A directory whose number nothing beside it carries is reported with the
    reason, rather than left to look like one more lesson nobody can read.
    """
    lesson = corpus / BATCH / "0199"
    shutil.copytree(corpus / BATCH / "0110", lesson)
    (lesson / "englishpod_B0110.md").unlink()

    result = run_cli("preprocess", lesson)

    assert result.returncode == 1
    assert "carries no lesson code" in result.stderr
    assert "carries lesson 0199" in result.stderr
    assert not list(lesson.glob("*.md"))


def test_a_directory_holding_too_many_pdfs_names_a_few_of_them(
    tmp_path: Path, run_cli
) -> None:
    """A directory holding hundreds is one to look at, not a list to read.

    The corpus holds one such directory, so a run over it reports a single
    lesson and a message that stays one line long.
    """
    crowded = tmp_path / "crowded"
    crowded.mkdir()
    for number in range(7):
        (crowded / f"englishpod_{number}.pdf").write_bytes(b"")

    result = run_cli("preprocess", crowded)

    assert result.returncode == 1
    assert "holds more than one PDF" in result.stderr
    assert "and 4 more" in result.stderr
    assert len(result.stderr) < 200


# A lesson whose PDF holds no text at all is read back out of its pictures by
# the OCR pass, which is a pass of its own because it reaches a service over the
# network and costs money to call. Nothing here reaches one: `tests/stub_ocr.py`
# answers for it, and a page goes up and comes back the way a real page would.

SCANNED = "englishpod_C0109.md"
KEY, SECRET = "BAIDU_OCR_API_KEY", "BAIDU_OCR_SECRET_KEY"

# One page of an EnglishPod lesson, as the service answers it: a title carrying
# the code, two speakers, and a vocabulary table of three columns. The
# coordinates are the picture's own pixels -- the service measures a page in the
# image it was sent, not in the points a text layer is in -- and they are the
# ones lesson 0239's own second page answered with, near enough to be a fixture.
PAGE = [
    # The running head the printed lessons carry, which the text layer does not
    # and which spans the columns below it if it is left in.
    ("EnglishPod", 546.0, 209.0),
    ("Learn English on your Terms", 1212.0, 238.0),
    # The code as the service read it: a picture gives back a level letter's
    # case as it struck the service, and the corpus's own is capitalised.
    ("The Weekend - Adventure Sports (c0109)", 377.0, 493.0),
    ("A: Welcome to Adventure Tours. How may I help you?", 398.0, 623.0),
    ("B: I want to book a tour with adventure sports.", 401.0, 928.0),
    ("Key Vocabulary", 373.0, 1905.0),
    ("hot air", 398.0, 2078.0),
    ("P", 915.0, 2085.0),
    ("a huge balloon risen up", 1582.0, 2090.0),
    # Both cells wrap, and the next term follows a wider gap below them --
    # which is what tells the reader where one term ends and the next begins.
    ("balloon", 398.0, 2158.0),
    ("by hot air", 1582.0, 2170.0),
    ("jagged", 398.0, 2400.0),
    ("A", 915.0, 2407.0),
    ("having a sharp surface", 1582.0, 2405.0),
]

# The Markdown a text-layer lesson yields, down to the empty table it still
# prints: what the OCR pass produces is the same file with different words in it.
EXPECTED_SCAN = """\
# C0109

## Dialogue

A: Welcome to Adventure Tours. How may I help you?

B: I want to book a tour with adventure sports.

## Key Vocabulary

| Term | Part of speech | Definition |
| --- | --- | --- |
| hot air balloon | P | a huge balloon risen up by hot air |
| jagged | A | having a sharp surface |

## Supplementary Vocabulary

| Term | Part of speech | Definition |
| --- | --- | --- |
"""


def keyed(directory: Path, *, key: str | None = "stub-key", secret: str | None = "stub-secret") -> Path:
    """A directory to run from, holding the `.env` the OCR pass reads.

    The file is kept out of the repository, so a run is given a directory of its
    own to find it in rather than the one the tests are being run from.
    """
    lines = [f"{name}={value}" for name, value in ((KEY, key), (SECRET, secret)) if value]
    (directory / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


def test_a_lesson_with_no_text_layer_is_read_out_of_its_pictures(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """The pass writes the same Markdown a text-layer lesson yields."""
    service = StubOcr(PAGE)
    try:
        result = run_cli(
            "preprocess", scanned_lesson, "--ocr", "--ocr-url", service.url, cwd=keyed(tmp_path)
        )

        assert result.returncode == 0, result.stderr
        assert (scanned_lesson / SCANNED).read_text(encoding="utf-8") == EXPECTED_SCAN
        assert len(service.asked_for("/rest/2.0/ocr/v1/accurate")) == 1
    finally:
        service.close()


def test_a_missing_credentials_file_is_reported_before_anything_is_read(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """No key is a sentence to act on, and no page is sent looking for one."""
    service = StubOcr(PAGE)
    try:
        result = run_cli("preprocess", scanned_lesson, "--ocr", "--ocr-url", service.url, cwd=tmp_path)

        assert result.returncode == 1
        assert ".env" in result.stderr
        assert KEY in result.stderr and SECRET in result.stderr
        assert service.requests == []
        assert not (scanned_lesson / SCANNED).exists()
    finally:
        service.close()


def test_a_credentials_file_missing_one_value_says_which(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """Half a key is a different sentence from no file at all."""
    result = run_cli(
        "preprocess", scanned_lesson, "--ocr", cwd=keyed(tmp_path, secret=None)
    )

    assert result.returncode == 1
    assert SECRET in result.stderr
    assert KEY not in result.stderr


def test_an_ordinary_run_needs_no_credentials_and_sends_no_page(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """A page of pictures is still the run's own business, and says so."""
    service = StubOcr(PAGE)
    try:
        result = run_cli("preprocess", scanned_lesson, "--ocr-url", service.url, cwd=tmp_path)

        assert result.returncode == 1
        assert "has no text layer; it needs the OCR pass" in result.stderr
        assert service.requests == []
    finally:
        service.close()


def test_a_page_the_service_will_not_read_is_reported(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """A bad key or a spent quota is a message, not a traceback."""
    service = StubOcr(PAGE)
    service.refuse("Access token invalid or no longer valid")
    try:
        result = run_cli(
            "preprocess", scanned_lesson, "--ocr", "--ocr-url", service.url, cwd=keyed(tmp_path)
        )

        assert result.returncode == 1
        assert "Access token invalid" in result.stderr
        assert not (scanned_lesson / SCANNED).exists()
    finally:
        service.close()


def test_an_unreachable_ocr_service_is_reported(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    result = run_cli(
        "preprocess", scanned_lesson, "--ocr", "--ocr-url", "http://127.0.0.1:1",
        cwd=keyed(tmp_path),
    )

    assert result.returncode == 1
    assert "cannot reach the OCR service" in result.stderr


def test_the_ocr_pass_leaves_an_existing_markdown_alone(
    scanned_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """A corrected Markdown is not re-read over by a pass that costs money."""
    mine = scanned_lesson / SCANNED
    mine.write_text("# C0109\n", encoding="utf-8")
    service = StubOcr(PAGE)
    try:
        result = run_cli(
            "preprocess", scanned_lesson, "--ocr", "--ocr-url", service.url, cwd=keyed(tmp_path)
        )

        assert mine.read_text(encoding="utf-8") == "# C0109\n"
        assert service.requests == []
        assert "already exists" in result.stdout
    finally:
        service.close()
