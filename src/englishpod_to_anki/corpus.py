"""Working through a whole corpus rather than one lesson at a time.

A stage pointed at the corpus directory has no list of lessons to follow: the
corpus's own layout is the list, and it is the only one that stays right as the
corpus grows. What the layout does not say out loud is where it stops nesting,
since the corpus's first families hold one lesson a directory and its later ones
nest them by the ten, so a lesson is recognised by what a directory holds -- the
lesson's PDF, its recordings, the Markdown the stages meet on -- and a directory
holding lessons beneath it is a container rather than a lesson of its own.

A run over hundreds of lessons meets lessons it cannot work with. Each is
skipped and named rather than allowed to stop the run, because a corpus-wide run
that reports the first unreadable lesson and abandons the other three hundred is
the thing the run exists to avoid. The one failure that does stop a run is the
collection itself: an Anki that cannot be reached or will not take a note is a
problem with the run, not with one lesson.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from .lesson import LessonError

# What a lesson directory holds: the lesson's PDF, its recordings, and the
# Markdown the stages meet on. Any one of them is enough to recognise a lesson
# by -- a lesson missing its dialogue audio is still a lesson, and one already
# preprocessed is one whose Markdown sits beside its PDF.
LESSON_FILES = ("*.pdf", "*.mp3", "*.md")

Result = TypeVar("Result")


def lessons(root: Path) -> tuple[Path, ...]:
    """Every lesson directory the corpus holds, in path order.

    Nothing marks a directory as a lesson's, so the layout decides: a directory
    holds a lesson when it holds a lesson's files and no lesson beneath it. The
    batch directories that nest the corpus's later lessons carry a combined PDF
    of the lessons they hold, and it is the lessons inside them that are the
    lessons, not the folder that gathers them.
    """
    return tuple(
        sorted(lesson for child in _children(root) for lesson in _lessons_under(child))
    )


def _lessons_under(directory: Path) -> list[Path]:
    """Every lesson directory at or under one directory.

    A directory holding lesson files is not a lesson when it holds lesson
    directories too: what it holds is the lessons, and the files beside them
    belong to no one lesson.
    """
    inside = [lesson for child in _children(directory) for lesson in _lessons_under(child)]
    if inside:
        return inside
    return [directory] if _holds_lesson_files(directory) else []


def _children(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir())


def _holds_lesson_files(directory: Path) -> bool:
    return any(any(directory.glob(pattern)) for pattern in LESSON_FILES)


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

    `halt` names the failures that belong to the collection rather than to one
    lesson. One of those stops the run where it happened, rather than being
    asked of every lesson left and answered the same way each time.
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
