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
from os.path import relpath
from pathlib import Path

from conftest import BATCH
from stub_anki import StubAnki


def notes(result: subprocess.CompletedProcess[str]) -> list[dict]:
    """The notes a build run emitted, one JSON document per line."""
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def lesson_codes(result: subprocess.CompletedProcess[str]) -> list[str]:
    """The lessons a build run emitted notes for, in the order it emitted them."""
    return [note["lesson_code"] for note in notes(result)]


def crowded(corpus: Path, name: str = "host text", files: int = 6) -> Path:
    """A directory of PDFs that is not a lesson, as the corpus's transcripts are."""
    directory = corpus / name
    directory.mkdir()
    for number in range(files):
        (directory / f"{number:03d} - A Customer.pdf").write_bytes(b"")
    return directory


def ignoring(corpus: Path, *entries: str) -> None:
    """Write the corpus's ignore file, the way its owner would."""
    (corpus / ".englishpodignore").write_text("\n".join(entries) + "\n", encoding="utf-8")


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


def test_a_lesson_that_cannot_be_read_at_all_does_not_stop_the_run(
    pdf_corpus: Path, run_cli
) -> None:
    """A corrupt file is a skipped lesson like any other, not a traceback.

    One of a run's lessons failing to open must not cost the run the lessons
    after it.
    """
    broken = pdf_corpus / "0001"
    broken.mkdir()
    (broken / "englishpod_B0001.pdf").write_bytes(b"not a PDF at all")

    result = run_cli("preprocess", pdf_corpus)

    assert result.returncode == 0, result.stderr
    assert (pdf_corpus / "0108" / "englishpod_D0108.md").is_file()
    assert f"cannot read {broken / 'englishpod_B0001.pdf'}" in result.stderr
    assert "preprocess: 3 lessons: 1 written, 2 skipped" in result.stderr


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


def test_a_directory_of_transcripts_beside_the_lessons_is_reported_once(
    pdf_corpus: Path, run_cli
) -> None:
    """The corpus keeps 178 host-transcript PDFs in a directory of their own.

    It is not a lesson, and the run neither takes it for one nor passes over it
    in silence: it is reported once, naming a few of its files and counting the
    rest rather than printing all 178.
    """
    transcripts = crowded(pdf_corpus)

    result = run_cli("preprocess", pdf_corpus)

    assert f"{transcripts} holds more than one PDF" in result.stderr
    assert "and 3 more" in result.stderr
    assert "preprocess: 3 lessons: 1 written, 2 skipped" in result.stderr


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


def test_an_ignored_directory_is_not_a_lesson_and_is_not_reported(
    corpus: Path, run_cli
) -> None:
    """A directory the owner declares out of scope is not looked at, or named."""
    transcripts = crowded(corpus)
    ignoring(corpus, "host text")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert str(transcripts) not in result.stderr
    # The four lessons the fixture holds, and not the transcript directory as a
    # fifth: the count is one lower than it is without the ignore file.
    assert "build: 4 lessons: 2 built, 2 skipped" in result.stderr


def test_an_ignore_file_leaves_the_rest_of_the_corpus_alone(corpus: Path, run_cli) -> None:
    """Whatever the file names, the lessons it does not are worked on as before."""
    ignoring(corpus, "0001")

    result = run_cli("build", corpus)

    assert lesson_codes(result) == ["C0108", "B0110"]
    assert "build: 3 lessons: 2 built, 1 skipped" in result.stderr
    # The ignored directory is gone from the summary rather than reported in it:
    # nothing was declined, because as far as the run is concerned it is not a
    # lesson.
    assert "0001" not in result.stderr


def test_a_path_entry_ignores_a_nested_directory(corpus: Path, run_cli) -> None:
    ignoring(corpus, f"{BATCH}/0111")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 2 built, 1 skipped" in result.stderr
    assert "F0111" not in lesson_codes(result)


def test_a_name_entry_ignores_a_directory_at_any_depth(corpus: Path, run_cli) -> None:
    """A bare name is matched wherever the directory sits, which is also how it
    over-matches: `0111` hides `{BATCH}/0111` without naming it."""
    ignoring(corpus, "0111")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 2 built, 1 skipped" in result.stderr
    assert "F0111" not in lesson_codes(result)


def test_an_absolute_path_in_the_ignore_file_names_the_same_directory(
    corpus: Path, run_cli
) -> None:
    """The path the owner has in front of them is the path they can write."""
    ignoring(corpus, f"{corpus / BATCH / '0111'}/")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 2 built, 1 skipped" in result.stderr


def test_comments_and_blank_lines_in_the_ignore_file_are_not_entries(
    corpus: Path, run_cli
) -> None:
    ignoring(corpus, "# 0111 was going to be ignored", "", "   ", "#0001")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 4 lessons: 2 built, 2 skipped" in result.stderr


def test_an_entry_that_matches_nothing_leaves_the_run_anyway(corpus: Path, run_cli) -> None:
    """A stale entry excludes nothing, and a directory comes back to the report.

    This is what keeps an ignore file's staleness loud: what it fails to exclude
    is discovered and named, rather than quietly missing from the run.
    """
    ignoring(corpus, "a directory that is not there")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 4 lessons: 2 built, 2 skipped" in result.stderr


def test_a_stage_pointed_at_an_ignored_directory_still_works(corpus: Path, run_cli) -> None:
    """An explicit path is not discovery: the directory pointed at is never asked.

    The file is read from the directory the stage is pointed at, and that
    directory is not tested against its own entries -- so a lesson named in the
    file beside it is still the lesson the stage was asked for.
    """
    ignoring(corpus / "0108", "0108")

    result = run_cli("build", corpus / "0108")

    assert result.returncode == 0, result.stderr
    assert lesson_codes(result) == ["C0108"]


def test_an_absolute_entry_names_the_directory_from_a_relative_root(
    corpus: Path, run_cli
) -> None:
    """The corpus can be given as a path relative to where the stage is run."""
    ignoring(corpus, str(corpus / "0108"))
    relative = Path(relpath(corpus, Path.cwd()))

    result = run_cli("build", relative)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 1 built, 2 skipped" in result.stderr
    assert "C0108" not in lesson_codes(result)


def test_an_entry_that_names_a_batch_directory_takes_its_lessons_with_it(
    corpus: Path, run_cli
) -> None:
    """The dangerous direction: an entry broad enough to hide several lessons.

    A batch directory is pruned before anything decides what it is, so ignoring
    one takes its lessons and its combined PDF out of the run together, and
    nothing surfaces to say so.
    """
    ignoring(corpus, BATCH)

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 2 lessons: 1 built, 1 skipped" in result.stderr
    assert lesson_codes(result) == ["C0108"]
    assert "F0111" not in result.stderr and "B0110" not in result.stderr


def test_a_byte_order_mark_does_not_disable_the_first_entry(corpus: Path, run_cli) -> None:
    """An editor that writes a byte-order mark must not silently drop an entry."""
    (corpus / ".englishpodignore").write_text("0108\n", encoding="utf-8-sig")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 1 built, 2 skipped" in result.stderr
    assert "C0108" not in lesson_codes(result)


def test_an_ignore_file_that_cannot_be_read_is_reported(corpus: Path, run_cli) -> None:
    """The owner is told the file cannot be read, rather than shown a traceback."""
    (corpus / ".englishpodignore").write_bytes("英语\n".encode("gbk"))

    result = run_cli("build", corpus)

    assert result.returncode == 1
    assert "cannot read" in result.stderr
    assert ".englishpodignore" in result.stderr
    assert "Traceback" not in result.stderr


def test_ignoring_every_lesson_of_a_batch_leaves_the_batch_directory_a_lesson(
    corpus: Path, run_cli
) -> None:
    """The lessons go; the directory that held them takes their place, reported.

    With its lessons excluded, the batch directory holds a combined PDF and no
    lesson beneath it, which is what a lesson directory looks like -- so it is
    reported as one rather than vanishing along with them.
    """
    ignoring(corpus, f"{BATCH}/0110", f"{BATCH}/0111")

    result = run_cli("build", corpus)

    assert result.returncode == 0, result.stderr
    assert "build: 3 lessons: 1 built, 2 skipped" in result.stderr
    assert f"{corpus / BATCH} holds no Markdown" in result.stderr
