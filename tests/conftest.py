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


@pytest.fixture
def run_cli():
    """Run the tool the way a user does: as a subprocess, through its command line.

    Standard input is empty unless a test has an answer to give, so that a run
    asking a question nobody meant it to ask reads an end of file rather than
    whatever the terminal running the tests happens to be holding.
    """

    def run(*arguments: object, input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "englishpod_to_anki", *(str(a) for a in arguments)],
            capture_output=True,
            text=True,
            input=input,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )

    return run
