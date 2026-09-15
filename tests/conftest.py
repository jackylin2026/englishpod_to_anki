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

# The tool's own reading of a lesson directory, imported by name rather than as
# a module: `lesson` is a fixture here, and a fixture would shadow it. A fixture
# is put in the state a run would leave it in with the tool's own rules rather
# than with rules invented beside them.
from englishpod_to_anki.lesson import (
    LessonError,
    lesson_markdowns,
    read_markdown,
    transcript_file,
)
from englishpod_to_anki.paths import BUILD

REPOSITORY = Path(__file__).resolve().parent.parent
SRC = REPOSITORY / "src"
FIXTURES = REPOSITORY / "tests" / "fixtures"
SAMPLE_LESSON = FIXTURES / "lesson"
SCANNED_LESSON = FIXTURES / "scanned_lesson"
MARKDOWN_LESSON = FIXTURES / "markdown_lesson"
CORPUS = FIXTURES / "corpus"
PRINT_TRANSCRIPT = FIXTURES / "transcript.pdf"

# The corpus fixture's batch directory: the layout the corpus nests its later
# lessons in, which a run has to tell apart from a lesson.
BATCH = "0110-0111"


@pytest.fixture
def lesson(tmp_path: Path) -> Path:
    """A copy of the sample lesson directory, free to be written into."""
    return _copied(SAMPLE_LESSON, tmp_path)


@pytest.fixture
def markdown_lesson(tmp_path: Path) -> Path:
    """A copy of the lesson that exists as Markdown rather than as a PDF.

    Its own directory holds the dialogue audio and no Markdown, as a lesson
    directory in the corpus does: the Markdown is the tool's own file, so it sits
    where a run would have put it -- in the build directory, under the lesson's
    own name.
    """
    return _seeded(_copied(MARKDOWN_LESSON, tmp_path), tmp_path)


@pytest.fixture
def scanned_lesson(tmp_path: Path) -> Path:
    """A copy of the image-only lesson directory, free to be written into."""
    return _copied(SCANNED_LESSON, tmp_path)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A copy of the corpus fixture, free to be written into.

    It carries what the real corpus does: lessons one or two directories deep,
    the batch directories that nest them carrying a combined PDF of their own,
    and a directory holding something that is not a lesson at all. Each lesson's
    Markdown is put where the corpus keeps the ones it has already: in the build
    directory.
    """
    return _seeded(_copied(CORPUS, tmp_path), tmp_path)


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


def _seeded(root: Path, tmp_path: Path) -> Path:
    """Move the Markdowns under `root` into the build directory, as a run names them.

    A fixture is drawn the way the corpus was before the tool kept its own files
    apart -- a Markdown beside the lesson's PDF -- and this is the migration the
    corpus's own Markdowns went through: each file moved into the lesson's build
    directory and renamed for the code it carries, so that the lesson holds the
    one file a run would write there and no second one beside it. A Markdown
    that carries no code keeps the name it has: it is a lesson the tool cannot
    build, and a run is expected to say so about it.
    """
    # The root is a lesson directory as often as it is a corpus, and a walk of
    # what is under a directory never yields the directory itself.
    directories = [root, *(d for d in sorted(root.rglob("*")) if d.is_dir())]
    for directory in directories:
        for held in lesson_markdowns(directory):
            try:
                name = f"englishpod_{read_markdown(held).code}.md"
            except LessonError:
                name = held.name
            build = built_dir(directory, tmp_path)
            build.mkdir(parents=True, exist_ok=True)
            moved = build / name
            beside = transcript_file(held)
            held.replace(moved)
            if beside.exists():
                beside.replace(transcript_file(moved))
    return root


def built_dir(lesson_dir: Path, tmp_path: Path) -> Path:
    """Where a run pointed at this lesson keeps what it writes about it.

    The directory the tool is given for the test's run, and the subdirectory it
    makes for the lesson -- which is named for the lesson's own directory, not for
    the code inside it, since the code is only known once the lesson has been read.
    """
    return tmp_path / BUILD_DIR / lesson_dir.name


def markdown_file(lesson_dir: Path, tmp_path: Path) -> Path:
    """The Markdown a lesson has in the build directory, read back.

    Found rather than named: it is called after the code inside the lesson, which
    is not the name of the directory it sits in. The print transcript's file for
    the lesson sits beside it, and is told apart by its name, as the tool tells
    them apart.
    """
    directory = built_dir(lesson_dir, tmp_path)
    (path,) = [
        held
        for held in directory.glob("englishpod_*.md")
        if not held.name.endswith(".transcript.md")
    ]
    return path


@pytest.fixture
def print_transcript() -> Path:
    """The corpus's print transcript, as a fixture: a condensation, read only.

    It holds four lessons' dialogues -- the sample lesson's own, one whose code it
    letters its own way, one it reads differently, and one no corpus holds -- and
    no vocabulary at all.
    """
    return PRINT_TRANSCRIPT


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


# The two stages that build a card -- and so ask what a word sounds like. A
# test's own transcriptions file sits beside the test's other files.
CARD_STAGES = ("build", "import")
TRANSCRIPTIONS = "transcriptions.tsv"

# Where every stage keeps what it writes. It is the test's own directory, since
# the tool would otherwise write into the repository's own build directory,
# which belongs to the learner.
BUILD_DIR = "build"

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
            # The build directory is the test's, said in the environment so that a
            # run made from the repository -- and a `.env` in it, naming the
            # learner's own -- cannot send a test's files there.
            env={
                **os.environ,
                "PYTHONPATH": str(SRC),
                BUILD: str(tmp_path / BUILD_DIR),
            },
        )

    return run


def _kept_local(arguments: tuple[object, ...], tmp_path: Path) -> list[str]:
    """One run's arguments, with a card stage given a file and no network.

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
