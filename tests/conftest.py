"""Shared plumbing for the command-line tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from stub_anki import StubAnki

REPOSITORY = Path(__file__).resolve().parent.parent
SRC = REPOSITORY / "src"
FIXTURES = REPOSITORY / "tests" / "fixtures"
SAMPLE_LESSON = FIXTURES / "lesson"
SCANNED_LESSON = FIXTURES / "scanned_lesson"
MARKDOWN_LESSON = FIXTURES / "markdown_lesson"
CORPUS = FIXTURES / "corpus"

# The corpus fixture's batch directory: the layout the corpus nests its later
# lessons in, which a run has to tell apart from a lesson.
BATCH = "0110-0111"


@pytest.fixture
def lesson(tmp_path: Path) -> Path:
    """A copy of the sample lesson directory, free to be written into."""
    return _copied(SAMPLE_LESSON, tmp_path)


@pytest.fixture
def markdown_lesson(tmp_path: Path) -> Path:
    """A copy of the lesson that exists as Markdown, beside its dialogue audio."""
    return _copied(MARKDOWN_LESSON, tmp_path)


@pytest.fixture
def scanned_lesson(tmp_path: Path) -> Path:
    """A copy of the image-only lesson directory, free to be written into."""
    return _copied(SCANNED_LESSON, tmp_path)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A copy of the corpus fixture, free to be written into.

    It carries what the real corpus does: lessons one or two directories deep,
    the batch directories that nest them carrying a combined PDF of their own,
    and a directory holding something that is not a lesson at all.
    """
    return _copied(CORPUS, tmp_path)


@pytest.fixture
def pdf_corpus(tmp_path: Path) -> Path:
    """A corpus of lessons that are PDFs: one with a text layer, one scan."""
    root = tmp_path / "corpus"
    _copied_into(SAMPLE_LESSON, root / "0108")
    _copied_into(SCANNED_LESSON, root / BATCH / "0109")
    return root


def _copied(source: Path, tmp_path: Path) -> Path:
    return _copied_into(source, tmp_path / source.name)


def _copied_into(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


@pytest.fixture
def anki():
    """A stub AnkiConnect, answering and recording what the tool asks of it."""
    stub = StubAnki()
    yield stub
    stub.close()


@pytest.fixture
def stub():
    """Stub AnkiConnects holding the notes a test puts there, closed at the end.

    A test that has notes to put in the collection says them first -- the ones
    the collection already holds -- and gets back the stub to assert on.
    """
    made: list[StubAnki] = []

    def build(*notes: dict, **collection: Any) -> StubAnki:
        instance = StubAnki(notes=notes, **collection)
        made.append(instance)
        return instance

    yield build
    for instance in made:
        instance.close()


# The stages that build a card, and so the ones that ask what a word sounds
# like. A test's own transcriptions file sits beside the test's other files.
CARD_STAGES = ("build", "import")
TRANSCRIPTIONS = "transcriptions.tsv"

# The flags that say where a card-building run looks for a transcription.
DICTIONARY_FLAGS = ("--transcriptions", "--dictionary-url", "--wiktionary-url", "--offline")


@pytest.fixture
def transcriptions(tmp_path: Path) -> Path:
    """The file one test's runs keep what they learned about words in."""
    return tmp_path / TRANSCRIPTIONS


@pytest.fixture
def run_cli(tmp_path: Path):
    """Run the tool the way a user does: as a subprocess, through its command line.

    Standard input is empty unless a test has an answer to give, so that a run
    asking a question nobody meant it to ask reads an end of file rather than
    whatever the terminal running the tests happens to be holding.

    A card-building run is kept to the test: it is given a transcriptions file
    of its own, since the tool would otherwise write what it looked up into the
    repository's own file, which belongs to the learner; and it is run offline
    unless the test says where a dictionary answers, so that a test which is not
    about the dictionaries cannot quietly reach one over the network. A test
    that names either of those is taken at its word.
    """

    def run(
        *arguments: object, input: str = "", cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "englishpod_to_anki", *_kept_local(arguments, tmp_path)],
            capture_output=True,
            text=True,
            input=input,
            cwd=cwd,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )

    return run


def _kept_local(arguments: tuple[object, ...], tmp_path: Path) -> list[str]:
    """One run's arguments, with a card-building stage given a file and no network.

    The two are decided apart: the file is always the test's, since a test has
    no business writing the learner's, while the network is only avoided when
    the test has said nothing about where a dictionary is.
    """
    run = [str(argument) for argument in arguments]
    if not arguments or arguments[0] not in CARD_STAGES:
        return run
    named = {
        str(argument).partition("=")[0] for argument in arguments if str(argument).startswith("-")
    }
    if "--transcriptions" not in named:
        run += ["--transcriptions", str(tmp_path / TRANSCRIPTIONS)]
    if not named & (set(DICTIONARY_FLAGS) - {"--transcriptions"}):
        run.append("--offline")
    return run
