"""A stage pointed at a corpus rather than at one lesson.

The corpus fixture is laid out the way the real one is: lessons one or two
directories deep, the batch directories that nest them carrying a combined PDF
of their own, and a directory beside them holding something that is not a
lesson. Nothing marks a directory as a lesson's, so the layout decides which
ones are the lessons.

The fixture also holds a lesson that cannot be built and a lesson missing its
dialogue audio, so that every run has something to skip. What a run skips is
reported at the end, since a run over hundreds of lessons is one whose silences
matter more than its noise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from conftest import BATCH
from stub_anki import StubAnki


def notes(result: subprocess.CompletedProcess[str]) -> list[dict]:
    """The notes a build run emitted, one JSON document per line."""
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def lesson_codes(result: subprocess.CompletedProcess[str]) -> list[str]:
    """The lessons a build run emitted notes for, in the order it emitted them."""
    return [note["lesson_code"] for note in notes(result)]


def test_a_run_builds_every_lesson_the_corpus_holds(corpus: Path, run_cli) -> None:
    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    # The lesson whose Markdown carries no code and the one with no dialogue
    # audio are missing, and every other lesson is here.
    assert lesson_codes(result) == ["C0108", "B0110"]


def test_a_batch_directory_is_not_a_lesson_of_its_own(corpus: Path, run_cli) -> None:
    """The batch directories that nest lessons carry a combined PDF of them.

    That PDF belongs to no lesson, so the directory holding it is a container
    rather than one more lesson the run has to skip.
    """
    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "4 lessons" in result.stderr
    assert f"{corpus / BATCH} holds" not in result.stderr


def test_a_lesson_missing_its_dialogue_audio_is_skipped_rather_than_built(
    corpus: Path, run_cli
) -> None:
    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "F0111" not in lesson_codes(result)
    assert f"{corpus / BATCH / '0111'} holds no dialogue audio" in result.stderr


def test_a_lesson_with_no_vocabulary_to_blank_is_skipped_rather_than_built(
    corpus: Path, run_cli
) -> None:
    """A card with nothing blanked looks complete and tests nothing.

    This lesson's Key Vocabulary table is missing entirely; `test_build` covers
    the other way a lesson has nothing to blank, a table whose terms the
    dialogue never says.
    """
    lesson = corpus / "0108"
    (lesson / "englishpod_D0108.md").write_text(
        "# C0108\n"
        "\n"
        "## Dialogue\n"
        "\n"
        "A: The stockroom needs a good clean before the audit.\n"
        "\n"
        "## Supplementary Vocabulary\n"
        "\n"
        "| Term | Part of speech | Definition |\n"
        "| --- | --- | --- |\n"
        "| ledger | common noun, singular | a book of accounts |\n",
        encoding="utf-8",
    )

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "C0108" not in lesson_codes(result)
    assert f"{lesson} has no vocabulary to draw blanks from" in result.stderr


def test_one_malformed_lesson_does_not_stop_the_run(corpus: Path, run_cli) -> None:
    """The fixture's first lesson carries no lesson code, and is not the last."""
    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert lesson_codes(result) == ["C0108", "B0110"]
    assert f"{corpus / '0001' / 'englishpod_B0001.md'} carries no lesson code" in result.stderr


def test_the_run_ends_with_a_summary_of_what_it_skipped_and_why(
    corpus: Path, run_cli
) -> None:
    result = run_cli("build", corpus)

    assert "build: 4 lessons: 2 built, 2 skipped" in result.stderr
    skipped = result.stderr.split("skipped:\n", 1)[1].splitlines()
    assert len(skipped) == 2
    assert any("0001" in line and "no lesson code" in line for line in skipped)
    assert any("0111" in line and "no dialogue audio" in line for line in skipped)


def test_a_run_that_worked_on_no_lesson_at_all_says_so_in_its_exit_code(
    corpus: Path, run_cli
) -> None:
    """Nothing done is not success, however many lessons were looked at."""
    for audio in corpus.glob("**/*dg.mp3"):
        audio.unlink()

    result = run_cli("build", corpus)

    assert result.returncode == 1
    assert "build: 4 lessons: 4 skipped" in result.stderr


def test_pointing_at_one_lesson_is_still_a_run_over_one_lesson(
    corpus: Path, run_cli
) -> None:
    """A lesson directory is worked on directly, with no summary around it."""
    result = run_cli("build", corpus / "0108")

    assert result.returncode == 0, result.stderr
    assert lesson_codes(result) == ["C0108"]
    assert "lessons" not in result.stderr


def test_a_directory_holding_one_lesson_is_a_run_over_one_lesson(
    corpus: Path, run_cli
) -> None:
    """Pointed at a batch directory, the run works on the lessons inside it."""
    shutil.rmtree(corpus / BATCH / "0111")

    result = run_cli("build", corpus / BATCH)

    assert result.returncode == 0, result.stderr
    assert lesson_codes(result) == ["B0110"]
    assert "build: 1 lesson: 1 built" in result.stderr


def test_import_sends_a_note_for_every_lesson_it_builds(corpus: Path, anki, run_cli) -> None:
    result = run_cli("import", corpus, "--anki-url", anki.url)

    assert result.returncode == 0, result.stderr
    tags = [request["note"]["tags"] for request in anki.sent("addNote")]
    assert tags == [["englishpod::C0108"], ["englishpod::B0110"]]
    assert "import: 4 lessons: 2 imported, 2 skipped" in result.stderr


def test_a_skipped_lesson_is_never_sent_to_anki(corpus: Path, anki, run_cli) -> None:
    """A lesson the tool declined to build leaves no trace in the collection."""
    result = run_cli("import", corpus, "--anki-url", anki.url)

    # Four lessons, two notes: the ones that could be built, and no others.
    assert len(anki.sent("addNote")) == 2
    assert len(anki.sent("storeMediaFile")) == 2
    assert f"{corpus / BATCH / '0111'} holds no dialogue audio" in result.stderr


def test_an_anki_that_refuses_a_note_stops_the_run(corpus: Path, run_cli) -> None:
    """A collection that will not take a note is not one lesson's problem.

    Half a corpus imported is worse than none, so the run stops and says how
    far it got rather than asking the same question of every lesson left.
    """
    stub = StubAnki()
    stub.refuse("addNote", "cannot create note because it is a duplicate")
    try:
        result = run_cli("import", corpus, "--anki-url", stub.url)

        assert result.returncode == 1
        assert "duplicate" in result.stderr
        # Nothing landed before it stopped, and it says where it stopped.
        assert f"import: 4 lessons: 1 skipped, stopped at {corpus / '0108'}" in result.stderr
        assert len(stub.sent("addNote")) == 1
    finally:
        stub.close()


def test_preprocess_runs_over_every_lesson_the_corpus_holds(pdf_corpus: Path, run_cli) -> None:
    result = run_cli("preprocess", pdf_corpus)

    assert result.returncode == 0, result.stderr
    written = pdf_corpus / "0108" / "englishpod_D0108.md"
    assert written.read_text(encoding="utf-8").startswith("# C0108\n")
    assert str(written) in result.stdout
    # The scan is reported with the reason, and the lesson with a text layer
    # is not held back by it.
    assert "preprocess: 2 lessons: 1 written, 1 skipped" in result.stderr
    assert f"{pdf_corpus / BATCH / '0109' / 'englishpod_C0109.pdf'} has no text layer" in (
        result.stderr
    )


def test_preprocess_counts_the_markdown_files_it_leaves_alone(
    pdf_corpus: Path, run_cli
) -> None:
    """A corpus-wide run does not overwrite a hand correction either."""
    assert run_cli("preprocess", pdf_corpus).returncode == 0

    result = run_cli("preprocess", pdf_corpus)

    assert result.returncode == 0, result.stderr
    assert "wrote" not in result.stdout
    assert "preprocess: 2 lessons: 1 already had a Markdown file, 1 skipped" in result.stderr
