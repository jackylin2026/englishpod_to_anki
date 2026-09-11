"""Preprocess, tested the only way the spec allows: through the command line.

Every test runs the tool as a subprocess against the sample lesson directory and
asserts on the Markdown it wrote, never on the tool's internals. The sample
lesson is drawn by `tests/fixtures/make_sample_lesson.py`.

The sample lesson's file is named for lesson D0108 while the code printed inside
it reads C0108, which is the disagreement the corpus really has.
"""

from __future__ import annotations

from pathlib import Path

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

A: You’ve made your point."""

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
    assert sorted(path.name for path in lesson.iterdir()) == [
        "englishpod_D0108.md",
        "englishpod_D0108.pdf",
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


def test_the_three_stages_are_separately_runnable(lesson: Path, run_cli) -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    for stage in ("preprocess", "build", "import"):
        assert stage in result.stdout

    # build and import are wired up but not built yet, and say so rather than passing silently.
    for stage in ("build", "import"):
        unfinished = run_cli(stage, lesson)
        assert unfinished.returncode == 1
        assert unfinished.stderr.strip()
