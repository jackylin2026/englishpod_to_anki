"""Build, tested through the command line like every other stage.

The stage's product is the note it would create, emitted as a JSON document on
stdout and asserted on here: the dialogue with its blanks, the glossary, the
audio it references, and the terms it could not place. `tests/fixtures/markdown_lesson`
is the sample lesson it reads; the file's dialogue exercises a term the page
wrapped, an inflected term, a bracketed term and a term the dialogue never
carries.

The lesson is named D0108 on disk while the code inside it reads C0108, which is
the disagreement the corpus really has.
"""

from __future__ import annotations

import json
import re
from os.path import relpath
from pathlib import Path

FIELDS = ["Sentences", "Phonetic symbols", "Words", "Synonym", "Word Family", "TTS"]

# The dialogue as the card's field carries it: a paragraph break is a newline
# before the break, an intra-paragraph wrap is a space before it, and every
# occurrence of a Key Vocabulary term is a blank.
SENTENCES = (
    "A: Morning, Ed. The auditors arrive on Monday, and I <br>"
    "want the {{c1::stockroom}} {{c1::immaculate}} before they get here. <br>"
    "Sales have {{c1::plunged}} since the spring audit.\n<br>"
    "B: I have been dreading this. Half the pallets are <br>"
    "still unlabelled and the shutter is jammed.\n<br>"
    "A: Then get the labels printed today. Move the <br>"
    "overflow into the {{c1::stockroom}} annex before the audit.\n<br>"
    "B: And the damaged crates? We cannot simply {{c1::write <br>off}} the damaged stock "
    "without a signature.\n<br>"
    "A: We are {{c1::overstocked}} and the regulations {{c1::governing}} <br>"
    "compensation are new, so we book an {{c1::open mic <br>night}} in the annex instead."
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


def built(lesson: Path, run_cli, *arguments: object) -> dict:
    """Run build over the sample lesson and return the note it emitted."""
    result = run_cli("build", lesson, *arguments)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_lesson_becomes_the_note_the_card_design_calls_for(
    markdown_lesson: Path, run_cli
) -> None:
    note = built(markdown_lesson, run_cli)

    assert note["lesson_code"] == "C0108"
    assert note["deck"] == "EnglishPod"
    assert note["note_type"] == "EnglishPod Cloze"
    assert list(note["fields"]) == FIELDS
    # The two fields the design carries empty, and the ones it fills.
    assert note["fields"]["Synonym"] == ""
    assert note["fields"]["Word Family"] == ""
    assert note["fields"]["Phonetic symbols"] == ""


def test_the_dialogue_breaks_where_the_page_broke(markdown_lesson: Path, run_cli) -> None:
    note = built(markdown_lesson, run_cli)

    assert note["fields"]["Sentences"] == SENTENCES


def test_a_term_the_page_wrapped_is_blanked_across_the_wrap(
    markdown_lesson: Path, run_cli
) -> None:
    """`write off` ends one physical line and `open mic night` spans two."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    assert "{{c1::write <br>off}}" in sentences
    assert "{{c1::open mic <br>night}}" in sentences


def test_an_inflected_term_is_blanked(markdown_lesson: Path, run_cli) -> None:
    """`govern` is on the table; `governing` is what the dialogue says."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    assert "{{c1::governing}}" in sentences


def test_a_term_that_ends_in_e_finds_its_past_tense(markdown_lesson: Path, run_cli) -> None:
    """`plunge` takes a `d`; it does not take the `ed` a bare suffix would add."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    assert "{{c1::plunged}}" in sentences


def test_a_bracketed_annotation_does_not_prevent_a_match(
    markdown_lesson: Path, run_cli
) -> None:
    """The table says `(be) overstocked`; the dialogue says `overstocked`."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    assert "{{c1::overstocked}}" in sentences


def test_every_occurrence_of_a_term_is_blanked(markdown_lesson: Path, run_cli) -> None:
    """`stockroom` is said twice, and the learner is asked for it twice."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    assert sentences.count("{{c1::stockroom}}") == 2


def test_a_term_the_dialogue_never_carries_is_reported_not_blanked(
    markdown_lesson: Path, run_cli
) -> None:
    result = run_cli("build", markdown_lesson)
    note = json.loads(result.stdout)

    assert note["unmatched_terms"] == ["lay it on me"]
    assert "lay it on me" not in note["fields"]["Sentences"]
    # Reported to the reader, not only to whoever reads the JSON.
    assert "lay it on me" in result.stderr


def test_a_supplementary_term_feeds_the_glossary_but_never_a_blank(
    markdown_lesson: Path, run_cli
) -> None:
    """The dialogue says `dreading` and `crates`; neither may become a blank."""
    note = built(markdown_lesson, run_cli)

    assert "{{c1::dreading}}" not in note["fields"]["Sentences"]
    assert "{{c1::crates}}" not in note["fields"]["Sentences"]
    assert "dread -&gt; to fear something" in note["fields"]["Words"]
    assert "crate -&gt; a wooden box for moving goods" in note["fields"]["Words"]


def test_the_glossary_covers_both_vocabulary_tables(markdown_lesson: Path, run_cli) -> None:
    note = built(markdown_lesson, run_cli)

    assert note["fields"]["Words"] == GLOSSARY


def test_the_whole_note_is_one_card(markdown_lesson: Path, run_cli) -> None:
    """Every blank shares one cloze number, which is what makes one card."""
    sentences = built(markdown_lesson, run_cli)["fields"]["Sentences"]

    blanks = re.findall(r"\{\{c(\d+)::", sentences)
    assert blanks
    assert set(blanks) == {"1"}


def test_the_dialogue_audio_is_attached_under_its_source_filename(
    markdown_lesson: Path, run_cli
) -> None:
    note = built(markdown_lesson, run_cli)

    assert note["audio"]["filename"] == "englishpod_D0108dg.mp3"
    assert note["fields"]["TTS"] == "[sound:englishpod_D0108dg.mp3]"
    # Nothing is renamed: the file uploaded is the one the corpus holds.
    assert Path(note["audio"]["path"]).name == note["audio"]["filename"]
    assert Path(note["audio"]["path"]).is_file()


def test_the_audio_path_is_absolute_even_for_a_relative_lesson(
    markdown_lesson: Path, run_cli
) -> None:
    """Anki opens the file in its own working directory, not the tool's."""
    relative = Path(relpath(markdown_lesson, Path.cwd()))

    note = built(relative, run_cli)

    assert Path(note["audio"]["path"]).is_absolute()
    assert note["audio"]["filename"] == "englishpod_D0108dg.mp3"


def test_the_note_carries_an_identity_derived_from_the_lesson_code(
    markdown_lesson: Path, run_cli
) -> None:
    """So that a later run finds the note an earlier run made."""
    note = built(markdown_lesson, run_cli)

    assert note["tags"] == ["englishpod::C0108"]
    # The identity is the code inside the lesson, not the name of its file.
    assert markdown_lesson.name != "C0108"


def test_a_lesson_preprocessed_from_its_pdf_builds(lesson: Path, run_cli) -> None:
    """The stages meet on the Markdown: what preprocess writes, build reads."""
    assert run_cli("preprocess", lesson).returncode == 0

    result = run_cli("build", lesson)
    assert result.returncode == 0, result.stderr
    note = json.loads(result.stdout)

    assert note["lesson_code"] == "C0108"
    assert "{{c1::immaculate}}" in note["fields"]["Sentences"]
    # `pallet` is on the table and the dialogue says `pallets`.
    assert "{{c1::pallets}}" in note["fields"]["Sentences"]
    # The dialogue splits `write off`, and never names the open mic night.
    assert note["unmatched_terms"] == ["write off", "open mic night"]


def test_a_lesson_with_no_markdown_is_reported(lesson: Path, run_cli) -> None:
    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no Markdown" in result.stderr


def test_a_markdown_with_no_lesson_code_is_reported(tmp_path: Path, run_cli) -> None:
    """The code is the note's identity, so a lesson without one cannot be built."""
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    (lesson / "englishpod_D0108.md").write_text("## Dialogue\n\nA: Hello.\n", encoding="utf-8")
    (lesson / "englishpod_D0108dg.mp3").write_bytes(b"")

    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no lesson code" in result.stderr
    assert not result.stdout


def test_a_lesson_with_no_dialogue_audio_is_reported(tmp_path: Path, run_cli) -> None:
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    (lesson / "englishpod_D0108.md").write_text("# C0108\n", encoding="utf-8")

    result = run_cli("build", lesson)

    assert result.returncode == 1
    assert "no dialogue audio" in result.stderr
