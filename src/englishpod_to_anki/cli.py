"""The command line: three stages, each runnable on its own.

A stage that cannot do its work says so and stops, with the stage's own name in
front of the reason: a lesson the tool cannot read, or a collection it cannot
reach, is something to act on rather than a traceback to read.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .anki import DEFAULT_URL, AnkiConnectError
from .card import Note, build_note
from .importer import send_note
from .lesson import LessonError
from .preprocess import preprocess_lesson


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preprocess":
            return _preprocess(args.lesson, force=args.force)
        if args.command == "build":
            return _build(args.lesson)
        return _import(args.lesson, url=args.anki_url)
    except (LessonError, AnkiConnectError) as error:
        print(f"{args.command}: {error}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="englishpod-to-anki",
        description="Turn a downloaded EnglishPod corpus into Anki cards.",
    )
    stages = parser.add_subparsers(dest="command", required=True)

    preprocess = stages.add_parser(
        "preprocess", help="write a lesson's Markdown beside its PDF"
    )
    preprocess.add_argument("lesson", type=Path, help="the lesson directory holding one PDF")
    preprocess.add_argument(
        "--force", action="store_true", help="regenerate a Markdown file that already exists"
    )

    build = stages.add_parser("build", help="show the note a lesson's Markdown makes")
    build.add_argument("lesson", type=Path, help="the lesson directory holding one Markdown")

    send = stages.add_parser("import", help="send a lesson's note to a running Anki")
    send.add_argument("lesson", type=Path, help="the lesson directory holding one Markdown")
    send.add_argument(
        "--anki-url",
        default=DEFAULT_URL,
        help=f"where AnkiConnect listens (default {DEFAULT_URL})",
    )
    return parser


def _preprocess(lesson: Path, *, force: bool) -> int:
    result = preprocess_lesson(lesson, force=force)
    if result.written:
        print(f"preprocess: wrote {result.markdown}")
    else:
        print(
            f"preprocess: {result.markdown} already exists; left untouched "
            "(pass --force to regenerate it)"
        )
    return 0


def _build(lesson: Path) -> int:
    note = build_note(lesson)
    print(json.dumps(note.as_json(), ensure_ascii=False))
    _report_unmatched(note)
    return 0


def _import(lesson: Path, *, url: str) -> int:
    note = build_note(lesson)
    note_id = send_note(note, url=url)
    print(f"import: {note.code}: added note {note_id} to the {note.deck} deck")
    _report_unmatched(note)
    return 0


def _report_unmatched(note: Note) -> None:
    """Name the terms no dialogue line carried, for whoever is watching.

    Both stages answer with the same report: it is a fact about the lesson, not
    about what was done with it.
    """
    if note.unmatched_terms:
        terms = ", ".join(note.unmatched_terms)
        print(f"{note.code}: no dialogue line carries {terms}", file=sys.stderr)
