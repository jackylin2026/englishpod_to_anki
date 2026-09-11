"""The command line: three stages, each runnable on its own."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .preprocess import PreprocessError, preprocess_lesson

STAGES = ("preprocess", "build", "import")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preprocess":
        return _preprocess(args.lesson, force=args.force)
    print(f"{args.command}: this stage is not built yet", file=sys.stderr)
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

    for stage in STAGES[1:]:
        stub = stages.add_parser(stage, help=f"{stage} one lesson")
        stub.add_argument("lesson", type=Path, help="the lesson directory")
    return parser


def _preprocess(lesson: Path, *, force: bool) -> int:
    try:
        result = preprocess_lesson(lesson, force=force)
    except PreprocessError as error:
        print(f"preprocess: {error}", file=sys.stderr)
        return 1
    if result.written:
        print(f"preprocess: wrote {result.markdown}")
    else:
        print(
            f"preprocess: {result.markdown} already exists; left untouched "
            "(pass --force to regenerate it)"
        )
    return 0
