"""Working through a whole corpus rather than one lesson at a time.

A stage pointed at the corpus directory has no list of lessons to follow: the
corpus's own layout is the list, and it is the one that stays right as the
corpus grows. What the layout does not say out loud is where it stops nesting,
since the corpus's first families hold one lesson a directory and its later ones
nest them by the ten, so a lesson is recognised by what a directory holds -- the
lesson's PDF, its recordings, the Markdown an older version of the tool wrote
beside them -- and a directory holding lessons beneath it is a container rather
than a lesson of its own.

The one thing the owner writes down is what is *not* a lesson: a directory named
in `.englishpodignore`. That much is safe to write down, because the two kinds
of list fail in opposite directions -- an exclusion that goes stale excludes
nothing, and the directory it named turns up in the run's report again.

A run over hundreds of lessons meets lessons it cannot work with. Each is
skipped and named rather than allowed to stop the run, because a corpus-wide run
that reports the first unreadable lesson and abandons the other three hundred is
the thing the run exists to avoid. The failures that do stop a run are the ones
no lesson left could get past: an Anki that cannot be reached or will not take a
note, and the OCR service that will not read a page. Those are problems with the
run rather than with one lesson.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from .lesson import LessonError

# What a lesson directory holds: the lesson's PDF, its recordings, and the
# Markdown an older version of the tool wrote beside the PDF. Any one of them is
# enough to recognise a lesson by -- a lesson missing its dialogue audio is still
# a lesson, and one whose Markdown has been moved to the build directory is still
# a lesson because its PDF and recordings are there.
LESSON_FILES = ("*.pdf", "*.mp3", "*.md")

# Where the corpus's owner declares a directory out of scope: one entry to a
# line, at the root a stage is pointed at. It is the one file the tool asks of a
# corpus it otherwise reads where it lies.
IGNORE_FILE = ".englishpodignore"

# What one of those declarations is asked of a directory the walk meets.
Ignored = Callable[[Path], bool]

Result = TypeVar("Result")


def lessons(root: Path, *, build: Path | None = None) -> tuple[Path, ...]:
    """Every lesson directory the corpus holds, in path order.

    Nothing marks a directory as a lesson's, so the layout decides: a directory
    holds a lesson when it holds a lesson's files and no lesson beneath it. The
    batch directories that nest the corpus's later lessons carry a combined PDF
    of the lessons they hold, and it is the lessons inside them that are the
    lessons, not the folder that gathers them.

    The one directory the layout cannot decide is the one the corpus's owner
    declares: a directory named in `.englishpodignore` is not a lesson, and the
    walk neither descends into it nor reports it.

    The other is the directory the tool keeps its own files in, when a run keeps
    it inside the corpus. It holds a Markdown per lesson, which is one of the
    things a lesson is recognised by, so a walk that did not pass over it would
    read the tool's own output as a corpus of lessons that hold no PDF.
    """
    ignored = _ignored(root)
    mine = _outside(build)
    return tuple(
        sorted(
            lesson
            for child in _children(root, ignored, mine)
            for lesson in _lessons_under(child, ignored, mine)
        )
    )


def _outside(build: Path | None) -> Ignored | None:
    """What says a directory is the tool's own, whatever path it is reached by."""
    if build is None:
        return None
    root = build.resolve()
    return lambda path: path.resolve() == root


def _lessons_under(
    directory: Path, ignored: Ignored, mine: Ignored | None
) -> list[Path]:
    """Every lesson directory at or under one directory.

    A directory holding lesson files is not a lesson when it holds lesson
    directories too: what it holds is the lessons, and the files beside them
    belong to no one lesson.
    """
    inside = [
        lesson
        for child in _children(directory, ignored, mine)
        for lesson in _lessons_under(child, ignored, mine)
    ]
    if inside:
        return inside
    return [directory] if _holds_lesson_files(directory) else []


def _children(
    directory: Path, ignored: Ignored, mine: Ignored | None = None
) -> list[Path]:
    """A directory's subdirectories, without the ones declared out of scope.

    An ignored directory is left out here rather than tested for later, so that
    it is neither descended into as a container nor taken for a lesson by the
    directory that holds it. The tool's own directory is left out the same way
    and for the same reason.
    """
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_dir() and not ignored(path) and not (mine and mine(path))
    )


def _holds_lesson_files(directory: Path) -> bool:
    return any(any(directory.glob(pattern)) for pattern in LESSON_FILES)


def _ignored(root: Path) -> Ignored:
    """Whether a directory is one the corpus's owner has declared out of scope.

    Matching is exact -- a name, or a path from the root -- and never a glob or
    a prefix, because a pattern that over-matches takes lessons out of every run
    without saying so. The direction to fail in is the other one: an entry that
    matches nothing leaves the run exactly as it was.
    """
    entries = _entries(root)
    return lambda directory: (
        directory.name in entries or _path_from(root, directory) in entries
    )


def _entries(root: Path) -> frozenset[str]:
    """The ignore file's entries, as written, with comments and blanks dropped.

    A file that cannot be read at all is the owner's to fix, and is reported the
    way every other unreadable thing is: the run stops and says so, rather than
    running on without the exclusions the file declares. It is read as UTF-8
    with its byte-order mark taken off, since it is written by hand in whatever
    editor its owner has.
    """
    path = root / IGNORE_FILE
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return frozenset()
    except (OSError, UnicodeDecodeError) as error:
        raise LessonError(f"cannot read {path}: {error}") from error
    return frozenset(_entry(line, root) for line in text.splitlines() if _is_entry(line))


def _is_entry(line: str) -> bool:
    text = line.strip()
    return bool(text) and not text.startswith("#")


def _entry(line: str, root: Path) -> str:
    """One line as what it names: a directory's name, or its path from the root.

    A path that lands under the corpus is kept as the path from the root, so
    that the way a person has the directory in front of them is a way they can
    write it down -- and so that it names the same directory whether the corpus
    was given to the stage as an absolute path or a relative one.
    """
    path = Path(line.strip())
    if not path.is_absolute():
        return str(path)
    under = _under_root(path, root)
    return under if under is not None else str(path)


def _under_root(path: Path, root: Path) -> str | None:
    """A path as the path from the root, or None when it is not under it at all."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def _path_from(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


@dataclass(frozen=True)
class Unfinished:
    """A lesson a run has nothing to show for, and the stage's reason for that.

    A lesson the stage declined to work on is one, and so is the lesson a run
    stopped at when the collection itself was in the way: the two differ in what
    the run does next rather than in what it tells a person. The reason is the
    stage's own, so that a run reports the lesson in the stage's words rather
    than in a summary's paraphrase of them.
    """

    lesson: Path
    reason: str


@dataclass(frozen=True)
class Run(Generic[Result]):
    """What a stage did with the lessons a corpus holds."""

    lessons: tuple[Path, ...]
    worked: tuple[Result, ...]
    skipped: tuple[Unfinished, ...]
    stopped: Unfinished | None = None

    @property
    def did_anything(self) -> bool:
        """Whether the run worked on a lesson at all."""
        return bool(self.worked)


def run(
    directories: Sequence[Path],
    work: Callable[[Path], Result],
    *,
    halt: tuple[type[Exception], ...] = (),
) -> Run[Result]:
    """Work through every lesson, skipping the ones the stage cannot work with.

    `halt` names the failures that belong to the run rather than to one lesson:
    a collection that cannot be reached or will not take a note, a service that
    will not read the next page. One of those stops the run where it happened,
    rather than being asked of every lesson left and answered the same way each
    time.
    """
    worked: list[Result] = []
    skipped: list[Unfinished] = []
    stopped: Unfinished | None = None
    for lesson in directories:
        try:
            worked.append(work(lesson))
        except LessonError as error:
            skipped.append(Unfinished(lesson, str(error)))
        except halt as error:
            stopped = Unfinished(lesson, str(error))
            break
    return Run(
        lessons=tuple(directories),
        worked=tuple(worked),
        skipped=tuple(skipped),
        stopped=stopped,
    )
