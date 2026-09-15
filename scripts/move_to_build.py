"""Move a corpus's Markdowns out of it and into the tool's build directory.

This is a one-off: the tool used to write each lesson's Markdown beside that
lesson's PDF, and now it writes them all under one build directory, a lesson to
a subdirectory. A corpus that was preprocessed by the old tool therefore has its
Markdown in the wrong place -- the stages look in the build directory and find
nothing -- and this is what moves them.

It is deliberately not part of the tool. It runs once, against one corpus, by
hand:

    python scripts/move_to_build.py --dry-run /path/to/corpus
    python scripts/move_to_build.py /path/to/corpus

Where the build directory is is read the way the tool reads it: `ENGLISHPOD_BUILD_DIR`
in the environment, or that name in the `.env` beside where this is run from, or
a `build` under it. A lesson's subdirectory is named for the lesson's own
directory, and the file inside it for the code the Markdown carries -- which is
also how a lesson whose Markdown was named after its PDF ends up named for the
code, since the code is what every later stage asks for.

Nothing is overwritten: a lesson whose build directory already holds a Markdown
is reported and left alone, since the one that is there is the one a run has
been writing to.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from englishpod_to_anki import paths  # noqa: E402
from englishpod_to_anki.corpus import lessons  # noqa: E402
from englishpod_to_anki.lesson import (  # noqa: E402
    LessonError,
    lesson_markdowns,
    read_markdown,
    transcript_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path, help="the corpus directory holding the lessons")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="say what would be moved without moving anything",
    )
    args = parser.parse_args(argv)

    build = paths.build_root()
    moved = 0
    held = 0
    for lesson in lessons(args.corpus, build=build):
        for markdown in lesson_markdowns(lesson):
            held += 1
            moved += _move(markdown, lesson, build, dry=args.dry_run)
    verb = "would move" if args.dry_run else "moved"
    print(f"{verb} {moved} of the corpus's {held} Markdown files into {build}")
    return 0


def _move(held: Path, lesson_dir: Path, build: Path, *, dry: bool) -> int:
    """Move one lesson's Markdown, saying so. Returns 1 when it moved."""
    try:
        code = read_markdown(held).code
    except LessonError as error:
        # A lesson the tool cannot build. Its Markdown still belongs with the
        # others -- the build directory is where a stage looks for it -- but it
        # keeps the name it has, there being no code to name it after.
        print(f"  no code, left named as it is: {error}")
        return _place(held, lesson_dir, held.name, build, dry=dry)
    return _place(held, lesson_dir, f"englishpod_{code}.md", build, dry=dry)


def _place(held: Path, lesson_dir: Path, name: str, build: Path, *, dry: bool) -> int:
    """Put one file where the tool keeps it, unless something is there already."""
    destination = build / lesson_dir.name / name
    if destination.exists() and destination.resolve() != held.resolve():
        print(f"  already there, left alone: {destination}")
        return 0
    if dry:
        print(f"  {held} -> {destination}")
        return 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    beside = transcript_file(held)
    held.replace(destination)
    if beside.exists():
        there = transcript_file(destination)
        if there.exists():
            print(f"  already there, left alone: {there}")
        else:
            beside.replace(there)
    print(f"  {held} -> {destination}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
