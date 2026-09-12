"""The print transcript's cross-check, tested through the command line.

The transcript fixture is drawn by `tests/fixtures/make_sample_lesson.py` with
the corpus's print transcript's geometry: two columns to a page, the page number
in the gutter, a lesson's title set larger than its dialogue. It holds four
lessons -- the sample lesson's own dialogue (C0108), the bicycle lesson under a
code lettered the print's own way (C0110), the kettle lesson read differently
(C0111), and one no corpus holds (C0199) -- and no vocabulary at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SAMPLE = "englishpod_D0108.md"
BESIDE = "englishpod_D0108.transcript.md"

# The print transcript's version of the sample lesson, as the file beside the
# Markdown holds it: a dialogue and nothing else -- no title, no vocabulary, and
# the print's own line breaks rather than the lesson's.
EXPECTED_TRANSCRIPT = """\
## Dialogue

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

A: We only hire at entry-level for this role.
"""


def test_a_lesson_the_transcript_covers_is_written_beside_its_markdown(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """One dialogue-only file per lesson it covers, holding the print's reading."""
    result = run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    beside = lesson / BESIDE
    assert str(beside) in result.stdout
    assert beside.read_text(encoding="utf-8") == EXPECTED_TRANSCRIPT
    # A dialogue-only file, not a lesson's Markdown: it opens at the section the
    # print's reading of a lesson is, and names no lesson.
    assert beside.read_text(encoding="utf-8").splitlines()[0] == "## Dialogue"


def test_a_lesson_the_print_agrees_with_is_not_reported(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """The sample lesson's own writing is the print's, so nothing is said."""
    run_cli("preprocess", lesson)
    written = (lesson / SAMPLE).read_text(encoding="utf-8")

    result = run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    assert "differs" not in result.stderr
    # The lesson's Markdown is the lesson's: the check writes nothing into it.
    assert (lesson / SAMPLE).read_text(encoding="utf-8") == written


def test_a_lesson_the_print_disagrees_with_is_reported_and_left_alone(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """A hand correction is a disagreement with the print, and neither wins."""
    run_cli("preprocess", lesson)
    corrected = (lesson / SAMPLE).read_text(encoding="utf-8").replace(
        "## Key Vocabulary", "A: And the auditors?\n\n## Key Vocabulary", 1
    )
    (lesson / SAMPLE).write_text(corrected, encoding="utf-8")

    result = run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    assert f"C0108: the print transcript's dialogue differs from the lesson's; see {lesson / BESIDE}" in result.stderr
    assert (lesson / SAMPLE).read_text(encoding="utf-8") == corrected


def test_the_card_built_from_a_reported_lesson_is_the_lesson_s_own(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """A disagreement is reported, never resolved: the card is the lesson's words."""
    run_cli("preprocess", lesson, "--print-transcript", print_transcript)
    room = lesson / "room"
    room.mkdir()
    shutil.copy(lesson / SAMPLE, room / SAMPLE)
    shutil.copy(lesson / "englishpod_D0108dg.mp3", room / "englishpod_D0108dg.mp3")

    result = run_cli("build", room, "--offline")

    assert result.returncode == 0, result.stderr
    assert "immaculate" in result.stdout
    assert "entry-level" in result.stdout


def test_a_lesson_the_transcript_does_not_cover_is_processed_unreported(
    scanned_lesson: Path, print_transcript: Path, run_cli
) -> None:
    """The print holds no dialogue for it, so there is nothing to compare."""
    (scanned_lesson / "englishpod_C0109.md").write_text(
        "# C0109\n\n## Dialogue\n\nA: This lesson is not in the print.\n", encoding="utf-8"
    )

    result = run_cli("preprocess", scanned_lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    assert "differs" not in result.stderr
    assert sorted(path.name for path in scanned_lesson.glob("*.md")) == ["englishpod_C0109.md"]


def test_a_lesson_the_transcript_cannot_be_read_for_gets_no_file(
    scanned_lesson: Path, print_transcript: Path, run_cli
) -> None:
    """A lesson the run skips is not a lesson the print was checked against."""
    result = run_cli("preprocess", scanned_lesson, "--print-transcript", print_transcript)

    assert result.returncode == 1
    assert "no text layer" in result.stderr
    assert list(scanned_lesson.glob("*.md")) == []
    assert list(scanned_lesson.glob("*.transcript.md")) == []


def test_the_transcript_file_is_not_the_lesson_markdown(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """A run over the lesson still reads the lesson's own Markdown."""
    run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    result = run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    assert "holds more than one Markdown" not in result.stderr
    assert (
        lesson / SAMPLE
    ).read_text(encoding="utf-8").startswith("# C0108\n")

    built = run_cli("build", lesson, "--offline")

    assert built.returncode == 0, built.stderr
    assert "immaculate" in built.stdout


def test_a_transcript_file_does_not_stand_in_for_a_deleted_markdown(
    corpus: Path, print_transcript: Path, run_cli
) -> None:
    """A lesson whose Markdown has gone is read again, file beside it or not."""
    run_cli("preprocess", corpus, "--print-transcript", print_transcript)
    lesson = corpus / "0110-0111" / "0110"
    (lesson / "englishpod_B0110.md").unlink()

    result = run_cli("preprocess", corpus, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    # The lesson comes back out of the batch's PDF rather than out of the file
    # the print transcript's reading of it is in.
    assert "holds more than one Markdown" not in result.stderr
    assert "carries no lesson code" not in result.stderr
    assert (lesson / "englishpod_C0110.md").is_file()


def test_a_transcript_file_written_by_hand_is_left_alone(
    lesson: Path, print_transcript: Path, run_cli
) -> None:
    """The file is the print's reading, written once: only --force asks for it again."""
    run_cli("preprocess", lesson, "--print-transcript", print_transcript)
    (lesson / BESIDE).write_text("## Dialogue\n\nA: My own reading.\n", encoding="utf-8")

    result = run_cli("preprocess", lesson, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    assert (lesson / BESIDE).read_text(encoding="utf-8") == "## Dialogue\n\nA: My own reading.\n"

    forced = run_cli("preprocess", lesson, "--print-transcript", print_transcript, "--force")

    assert forced.returncode == 0, forced.stderr
    assert (lesson / BESIDE).read_text(encoding="utf-8") == EXPECTED_TRANSCRIPT


def test_a_document_that_is_not_a_print_transcript_is_refused(
    lesson: Path, run_cli
) -> None:
    """A lesson's PDF carries vocabulary, and the print transcript carries none."""
    result = run_cli(
        "preprocess", lesson, "--print-transcript", lesson / "englishpod_D0108.pdf"
    )

    assert result.returncode == 1
    assert "not the print transcript" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(lesson.glob("*.md")) == []


def test_a_run_over_a_corpus_says_what_it_checked_and_what_disagreed(
    corpus: Path, print_transcript: Path, run_cli
) -> None:
    """The summary carries the count; the lessons that disagree are named."""
    result = run_cli("preprocess", corpus, "--print-transcript", print_transcript)

    assert result.returncode == 0, result.stderr
    # The fixture corpus's 0110 agrees with the print, its 0111 does not, and
    # 0110's own code is lettered the print's way -- the digits are what match.
    assert (corpus / "0110-0111" / "0110" / "englishpod_B0110.transcript.md").is_file()
    assert (
        corpus / "0110-0111" / "0111" / "englishpod_F0111.transcript.md"
    ).read_text(encoding="utf-8") == (
        "## Dialogue\n\nA: The kettle is broken once more.\n\n"
        "B: I will buy a new one tomorrow.\n"
    )
    assert f"{corpus / '0110-0111' / '0111' / 'englishpod_F0111.transcript.md'}" in result.stderr
    assert "1 of 2 disagreed with the print transcript" in result.stderr
    # The lesson the print carries and no corpus holds is not one of them.
    assert "0199" not in result.stderr
