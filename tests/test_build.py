"""Build, tested through the command line like every other stage.

The stage's product is the note it would create, written as a JSON document
beside the lesson's Markdown and asserted on here: the dialogue with its blanks,
the glossary, the audio it references, and the terms it could not place.
`tests/fixtures/markdown_lesson` is the sample lesson it reads; the file's
dialogue exercises a term the page wrapped, an inflected term, a bracketed term
and a term the dialogue never carries.

The lesson is named D0108 on disk while the code inside it reads C0108, which is
the disagreement the corpus really has.
"""

from __future__ import annotations

import json
import re
from functools import partial
from os.path import relpath
from pathlib import Path

import pytest

from conftest import built_dir

FIELDS = ["Sentences", "Phonetic symbols", "Words", "Synonym", "Word Family", "TTS"]

# The dialogue as the card's field carries it: a turn is one line however many
# lines the page printed it over, a turn is preceded by a blank line, and every
# occurrence of a Key Vocabulary term is a blank.
SENTENCES = (
    "A: Morning, Ed. The auditors arrive on Monday, and I "
    "want the {{c1::stockroom}} {{c1::immaculate}} before they get here. "
    "Sales have {{c1::plunged}} since the spring audit.\n<br>"
    "B: I have been dreading this. Half the pallets are "
    "still unlabelled and the shutter is jammed.\n<br>"
    "A: Then get the labels printed today. Move the "
    "overflow into the {{c1::stockroom}} annex before the audit.\n<br>"
    "B: And the damaged crates? We cannot simply {{c1::write off}} the damaged stock "
    "without a signature.\n<br>"
    "A: We are {{c1::overstocked}} and the regulations {{c1::governing}} "
    "compensation are new, so we book an {{c1::open mic night}} in the annex instead."
)

# The phonetic transcriptions: both tables in table order, one entry per
# single-word term and none for the phrases. Written out from a dictionary
# rather than pasted from the tool, as everything here is. `overstocked` and
# `immaculate` are where the offline dictionary's own stress marking is poor,
# and are what its file is for.
PHONETIC = (
    "/ˈstɑˌkrum/<br>/ˌɪˈmækjulɪt/<br>/ˈɡʌvɚn/<br>/ˈoʊvɚˈstɑkt/"
    "<br>/ˈplʌndʒ/<br>/ˈlɛdʒɚ/<br>/ˈdrɛd/<br>/ˈkreɪt/"
)

# The glossary: both tables, term, arrow, definition, in table order.
GLOSSARY = (
    "stockroom -&gt; the room where goods are kept<br>"
    "immaculate -&gt; perfectly clean<br>"
    "write off -&gt; to cancel a debt<br>"
    "open mic night -&gt; a slot where anyone may perform<br>"
    "govern -&gt; rule<br>"
    "(be) overstocked -&gt; having too many things to sell<br>"
    "plunge -&gt; drop down suddenly and quickly<br>"
    "lay it on me -&gt; tell me the bad news<br>"
    "ledger -&gt; a book of accounts<br>"
    "dread -&gt; to fear something<br>"
    "crate -&gt; a wooden box for moving goods"
)


def markdown(lesson: Path, tmp_path: Path, code: str = "C0108") -> Path:
    """The Markdown a build reads: the tool's own file, in the build directory."""
    directory = built_dir(lesson, tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"englishpod_{code}.md"


def wrote(lesson: Path, tmp_path: Path, code: str = "C0108") -> Path:
    """The note file a build leaves, in the lesson's directory in the build tree.

    Named for the code read out of the lesson rather than for the directory it
    sits in, which is the disagreement the corpus really has.
    """
    return built_dir(lesson, tmp_path) / f"englishpod_{code}.json"


def build(lesson: Path, run_cli, tmp_path: Path, *arguments: object) -> dict:
    """Run build over a lesson and return the note it wrote."""
    result = run_cli("build", lesson, *arguments)
    assert result.returncode == 0, result.stderr
    return json.loads(wrote(lesson, tmp_path).read_text(encoding="utf-8"))


# The two a test's own lesson needs to find what was written, given once so that
# every test below is about the note rather than about where it is.
@pytest.fixture
def built(markdown_lesson: Path, run_cli, tmp_path: Path):
    return partial(build, markdown_lesson, run_cli, tmp_path)


@pytest.fixture
def note_file(markdown_lesson: Path, tmp_path: Path) -> Path:
    """Where a build over the sample lesson leaves its note."""
    return wrote(markdown_lesson, tmp_path)


def test_a_lesson_becomes_the_note_the_card_design_calls_for(
    markdown_lesson: Path, run_cli, built
) -> None:
    note = built()

    assert note["lesson_code"] == "C0108"
    assert note["deck"] == "EnglishPod"
    assert note["note_type"] == "EnglishPod Cloze"
    assert list(note["fields"]) == FIELDS
    # The two fields the design carries empty, and the ones it fills.
    assert note["fields"]["Synonym"] == ""
    assert note["fields"]["Word Family"] == ""
    assert note["fields"]["Phonetic symbols"] == PHONETIC
    # Every one of the lesson's words is in the offline dictionary.
    assert note["untranscribed_terms"] == []


def test_the_note_is_written_into_the_lessons_directory_in_the_build_tree(
    markdown_lesson: Path, run_cli, note_file: Path
) -> None:
    """Named for the code inside the lesson, not for the file or the directory."""
    result = run_cli("build", markdown_lesson)

    assert result.returncode == 0, result.stderr
    assert note_file.is_file()
    # The path is said out loud, so a run over a corpus names what it wrote.
    assert f"build: wrote {note_file}" in result.stdout


def test_nothing_but_the_line_it_wrote_goes_to_stdout(
    markdown_lesson: Path, run_cli, note_file: Path
) -> None:
    """The document is the file's business now, and the terminal keeps its lines."""
    result = run_cli("build", markdown_lesson)

    assert result.stdout.splitlines() == [f"build: wrote {note_file}"]


def test_the_note_file_is_written_for_a_person_to_read(
    markdown_lesson: Path, run_cli, note_file: Path
) -> None:
    """Over its lines rather than as one, and in UTF-8 rather than in escapes."""
    assert run_cli("build", markdown_lesson).returncode == 0

    text = note_file.read_text(encoding="utf-8")

    assert text.endswith("\n")
    # The IPA reads as itself: an escape would hide what the field is for.
    assert "/ˈstɑˌkrum/" in text
    assert "\\u02c8" not in text
    assert json.loads(text)["fields"]["Sentences"] == SENTENCES


def test_a_rebuild_writes_over_the_note_it_wrote(
    markdown_lesson: Path, run_cli, built, note_file: Path
) -> None:
    """The file is the note this Markdown makes now, and a corrected Markdown
    would be contradicted by a stale note beside it."""
    note_file.write_text('{"lesson_code": "stale"}', encoding="utf-8")

    rebuilt = built()

    assert rebuilt["lesson_code"] == "C0108"


def test_the_dialogue_breaks_where_the_page_broke(markdown_lesson: Path, run_cli, built) -> None:
    note = built()

    assert note["fields"]["Sentences"] == SENTENCES


def test_a_term_the_page_wrapped_is_blanked_across_the_wrap(
    markdown_lesson: Path, run_cli, built
) -> None:
    """`write off` ends one physical line and `open mic night` spans two.

    What the page broke is not a break on the card -- a turn is one line -- so
    the blank carries the term's words with nothing between them but a space.
    """
    sentences = built()["fields"]["Sentences"]

    assert "{{c1::write off}}" in sentences
    assert "{{c1::open mic night}}" in sentences


def test_an_inflected_term_is_blanked(markdown_lesson: Path, run_cli, built) -> None:
    """`govern` is on the table; `governing` is what the dialogue says."""
    sentences = built()["fields"]["Sentences"]

    assert "{{c1::governing}}" in sentences


def test_a_term_that_ends_in_e_finds_its_past_tense(markdown_lesson: Path, run_cli, built) -> None:
    """`plunge` takes a `d`; it does not take the `ed` a bare suffix would add."""
    sentences = built()["fields"]["Sentences"]

    assert "{{c1::plunged}}" in sentences


def test_a_bracketed_annotation_does_not_prevent_a_match(
    markdown_lesson: Path, run_cli, built
) -> None:
    """The table says `(be) overstocked`; the dialogue says `overstocked`."""
    sentences = built()["fields"]["Sentences"]

    assert "{{c1::overstocked}}" in sentences


def test_every_occurrence_of_a_term_is_blanked(markdown_lesson: Path, run_cli, built) -> None:
    """`stockroom` is said twice, and the learner is asked for it twice."""
    sentences = built()["fields"]["Sentences"]

    assert sentences.count("{{c1::stockroom}}") == 2


def test_a_term_the_dialogue_never_carries_is_reported_not_blanked(
    markdown_lesson: Path, run_cli, note_file: Path
) -> None:
    result = run_cli("build", markdown_lesson)
    note = json.loads(note_file.read_text(encoding="utf-8"))

    assert note["unmatched_terms"] == ["lay it on me"]
    assert "lay it on me" not in note["fields"]["Sentences"]
    # Reported to the reader, not only to whoever reads the JSON.
    assert "lay it on me" in result.stderr


def test_a_supplementary_term_feeds_the_glossary_but_never_a_blank(
    markdown_lesson: Path, run_cli, built
) -> None:
    """The dialogue says `dreading` and `crates`; neither may become a blank."""
    note = built()

    assert "{{c1::dreading}}" not in note["fields"]["Sentences"]
    assert "{{c1::crates}}" not in note["fields"]["Sentences"]
    assert "dread -&gt; to fear something" in note["fields"]["Words"]
    assert "crate -&gt; a wooden box for moving goods" in note["fields"]["Words"]


def test_the_glossary_covers_both_vocabulary_tables(markdown_lesson: Path, run_cli, built) -> None:
    note = built()

    assert note["fields"]["Words"] == GLOSSARY


def test_the_whole_note_is_one_card(markdown_lesson: Path, run_cli, built) -> None:
    """Every blank shares one cloze number, which is what makes one card."""
    sentences = built()["fields"]["Sentences"]

    blanks = re.findall(r"\{\{c(\d+)::", sentences)
    assert blanks
    assert set(blanks) == {"1"}


def test_the_dialogue_audio_is_attached_under_its_source_filename(
    markdown_lesson: Path, run_cli, built
) -> None:
    note = built()

    assert note["audio"]["filename"] == "englishpod_D0108dg.mp3"
    assert note["fields"]["TTS"] == "[sound:englishpod_D0108dg.mp3]"
    # Nothing is renamed: the file uploaded is the one the corpus holds.
    assert Path(note["audio"]["path"]).name == note["audio"]["filename"]
    assert Path(note["audio"]["path"]).is_file()


def test_the_audio_path_is_absolute_even_for_a_relative_lesson(
    markdown_lesson: Path, run_cli, tmp_path: Path
) -> None:
    """Anki opens the file in its own working directory, not the tool's."""
    relative = Path(relpath(markdown_lesson, Path.cwd()))

    note = build(relative, run_cli, tmp_path)

    assert Path(note["audio"]["path"]).is_absolute()
    assert note["audio"]["filename"] == "englishpod_D0108dg.mp3"


def test_the_note_carries_an_identity_derived_from_the_lesson_code(
    markdown_lesson: Path, run_cli, built
) -> None:
    """So that a later run finds the note an earlier run made."""
    note = built()

    assert note["tags"] == ["englishpod::C0108"]
    # The identity is the code inside the lesson, not the name of its file.
    assert markdown_lesson.name != "C0108"


def test_a_lesson_preprocessed_from_its_pdf_builds(
    lesson: Path, run_cli, tmp_path: Path
) -> None:
    """The stages meet on the Markdown: what preprocess writes, build reads."""
    assert run_cli("preprocess", lesson).returncode == 0

    result = run_cli("build", lesson)
    assert result.returncode == 0, result.stderr
    note = json.loads(wrote(lesson, tmp_path).read_text(encoding="utf-8"))

    assert note["lesson_code"] == "C0108"
    assert "{{c1::immaculate}}" in note["fields"]["Sentences"]
    # `pallet` is on the table and the dialogue says `pallets`.
    assert "{{c1::pallets}}" in note["fields"]["Sentences"]
    # The dialogue splits `write off`, and never names the open mic night.
    assert note["unmatched_terms"] == ["write off", "open mic night"]


def test_a_note_that_cannot_be_written_is_a_lesson_nothing_was_shown_for(
    markdown_lesson: Path, run_cli, tmp_path: Path, note_file: Path
) -> None:
    """The file is all the stage leaves behind, so a lesson without one did not build."""
    wrote_dir = built_dir(markdown_lesson, tmp_path)
    wrote_dir.chmod(0o500)
    try:
        result = run_cli("build", markdown_lesson)
    finally:
        wrote_dir.chmod(0o700)

    assert result.returncode == 1
    assert f"cannot write {note_file}" in result.stderr
    assert "Traceback" not in result.stderr
    assert not result.stdout
    assert not note_file.exists()


def test_a_lesson_with_no_markdown_is_reported(lesson: Path, run_cli) -> None:
    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no Markdown" in result.stderr


def test_a_markdown_with_no_lesson_code_is_reported(tmp_path: Path, run_cli) -> None:
    """The code is the note's identity, so a lesson without one cannot be built."""
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    (lesson / "englishpod_D0108dg.mp3").write_bytes(b"")
    markdown(lesson, tmp_path).write_text("## Dialogue\n\nA: Hello.\n", encoding="utf-8")

    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no lesson code" in result.stderr
    assert not result.stdout
    assert not wrote(lesson, tmp_path).exists()


def test_a_lesson_with_no_dialogue_audio_is_reported(tmp_path: Path, run_cli) -> None:
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    markdown(lesson, tmp_path).write_text("# C0108\n", encoding="utf-8")

    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no dialogue audio" in result.stderr


def test_a_lesson_with_no_vocabulary_to_blank_is_reported(tmp_path: Path, run_cli) -> None:
    """A card with nothing blanked looks complete and tests nothing."""
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    markdown(lesson, tmp_path).write_text(
        "# C0108\n"
        "\n"
        "## Dialogue\n"
        "\n"
        "A: Nothing the table names is said here.\n"
        "\n"
        "## Key Vocabulary\n"
        "\n"
        "| Term | Part of speech | Definition |\n"
        "| --- | --- | --- |\n"
        "| stockroom | common noun, singular | the room where goods are kept |\n",
        encoding="utf-8",
    )
    (lesson / "englishpod_D0108dg.mp3").write_bytes(b"")

    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no vocabulary to draw blanks from" in result.stderr
    assert not result.stdout
    assert not wrote(lesson, tmp_path).exists()
