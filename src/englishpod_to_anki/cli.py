"""The command line: three stages, each runnable on its own.

A stage takes either a lesson directory or the corpus directory holding the
lessons, and works out which it was given from what the path holds; pointed at
the corpus, it works through every lesson in it and ends with a summary of the
ones it left alone.

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

from . import corpus, transcription
from .anki import DEFAULT_URL, AnkiConnectError
from .card import Note, build_note
from .importer import (
    ASK,
    IMPORTED,
    LEFT,
    POLICIES,
    REFRESHED,
    Done,
    Importer,
    Unanswered,
)
from .lesson import LessonError
from .ocr import BASE as OCR_URL, Baidu, OcrError, credentials
from .preprocess import Preprocessed, Reader, preprocess_lesson

# Every stage takes one path, which is either one lesson's directory or the
# corpus directory holding them all.
ONE_LESSON_OR_MANY = "a lesson directory, or the corpus directory holding them"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preprocess":
            return _preprocess(args.target, force=args.force, ocr=args.ocr, url=args.ocr_url)
        if args.command == "build":
            return _build(args.target, _transcriptions(args))
        return _import(
            args.target,
            url=args.anki_url,
            policy=args.existing,
            transcriptions=_transcriptions(args),
        )
    except (LessonError, AnkiConnectError, OcrError, Unanswered) as error:
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
    preprocess.add_argument("target", type=Path, help=ONE_LESSON_OR_MANY)
    preprocess.add_argument(
        "--force", action="store_true", help="regenerate a Markdown file that already exists"
    )
    preprocess.add_argument(
        "--ocr",
        action="store_true",
        help="read a lesson whose PDF holds no text with the OCR service, "
        "whose credentials are read from .env",
    )
    preprocess.add_argument(
        "--ocr-url",
        default=OCR_URL,
        help=f"where the OCR service answers (default {OCR_URL})",
    )

    build = stages.add_parser("build", help="show the note a lesson's Markdown makes")
    build.add_argument("target", type=Path, help=ONE_LESSON_OR_MANY)
    _transcription_flags(build)

    send = stages.add_parser("import", help="send a lesson's note to a running Anki")
    send.add_argument("target", type=Path, help=ONE_LESSON_OR_MANY)
    send.add_argument(
        "--anki-url",
        default=DEFAULT_URL,
        help=f"where AnkiConnect listens (default {DEFAULT_URL})",
    )
    send.add_argument(
        "--existing",
        choices=POLICIES,
        default=ASK,
        help="what to do about a lesson already in the collection (default: ask)",
    )
    _transcription_flags(send)
    return parser


def _transcription_flags(parser: argparse.ArgumentParser) -> None:
    """The flags saying where a word's phonetic transcription comes from.

    Both stages that build a card take them, because both build the same card:
    what a word sounds like is not something import knows that build does not.
    """
    parser.add_argument(
        "--transcriptions",
        type=Path,
        default=transcription.FILE,
        help="the file the resolved transcriptions are read from and written to "
        "(default: the one the tool ships beside its source)",
    )
    parser.add_argument(
        "--dictionary-url",
        default=transcription.DICTIONARY,
        help=f"where the free online dictionary answers (default {transcription.DICTIONARY})",
    )
    parser.add_argument(
        "--wiktionary-url",
        default=transcription.WIKTIONARY,
        help=f"where Wiktionary answers (default {transcription.WIKTIONARY})",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="transcribe from the offline dictionary and the file alone, asking "
        "neither online dictionary and reaching the network not at all",
    )


def _transcriptions(args: argparse.Namespace) -> transcription.Transcriptions:
    """What one run resolves words against, read before the run starts.

    Read before it rather than at the first lesson that meets a word, so that a
    file the tool cannot make sense of is said at once instead of after however
    many lessons it takes to reach a word that is not in the offline dictionary
    -- the same reason the OCR pass reads its credentials before its run.
    """
    return transcription.Transcriptions(
        args.transcriptions,
        dictionary=args.dictionary_url,
        wiktionary=args.wiktionary_url,
        offline=args.offline,
    )


def _preprocess(target: Path, *, force: bool, ocr: bool, url: str) -> int:
    reader = _ocr_pass(url) if ocr else None
    if not (lessons := corpus.lessons(target)):
        result = _preprocess_one(target, force=force, reader=reader)
        if not result.written:
            print(
                f"preprocess: {result.markdown} already exists; left untouched "
                "(pass --force to regenerate it)"
            )
        return 0

    run = corpus.run(
        lessons,
        lambda lesson: _preprocess_one(lesson, force=force, reader=reader),
        # A service that will not read the next page will not read the one after
        # it either, so the run stops where it happened rather than asking three
        # hundred more times and being refused the same way each time.
        halt=(OcrError,),
    )
    written = sum(result.written for result in run.worked)
    return _summarize(
        "preprocess",
        run,
        counts=(
            (written, "written"),
            (len(run.worked) - written, "already had a Markdown file"),
        ),
    )


def _ocr_pass(url: str) -> Reader:
    """The OCR pass, ready to read a page.

    Its credentials are read before the run rather than at the first lesson that
    needs them, so a run with no key says so at once instead of after however
    many lessons it takes to reach a page that holds no text.
    """
    key, secret = credentials()
    return Baidu(key=key, secret=secret, url=url).read


def _preprocess_one(lesson: Path, *, force: bool, reader: Reader | None) -> Preprocessed:
    """Write one lesson's Markdown, saying so when it wrote one.

    A run over a corpus reports the lessons it wrote a line each, so the saying
    so belongs to the lesson rather than to the run: a Markdown left as it was
    is reported by the run's summary instead, which does not repeat the way to
    regenerate it three hundred times over.
    """
    result = preprocess_lesson(lesson, force=force, reader=reader)
    if result.written:
        print(f"preprocess: wrote {result.markdown}")
    return result


def _build(target: Path, transcriptions: transcription.Transcriptions) -> int:
    if not (lessons := corpus.lessons(target)):
        _build_one(target, transcriptions)
        _report_lookups(transcriptions)
        return 0

    run = corpus.run(lessons, lambda lesson: _build_one(lesson, transcriptions))
    _report_lookups(transcriptions)
    return _summarize("build", run, counts=((len(run.worked), "built"),))


def _build_one(lesson: Path, transcriptions: transcription.Transcriptions) -> Note:
    note = build_note(lesson, transcribe=transcriptions.transcribe)
    print(json.dumps(note.as_json(), ensure_ascii=False))
    _report(note)
    return note


def _import(
    target: Path, *, url: str, policy: str, transcriptions: transcription.Transcriptions
) -> int:
    if not (lessons := corpus.lessons(target)):
        _import_one(target, Importer(url=url, policy=policy), transcriptions)
        _report_lookups(transcriptions)
        return 0

    importer = Importer(url=url, policy=policy, many=len(lessons) > 1)
    run = corpus.run(
        lessons,
        lambda lesson: _import_one(lesson, importer, transcriptions),
        halt=(AnkiConnectError, Unanswered),
    )
    _report_lookups(transcriptions)
    return _summarize(
        "import",
        run,
        counts=(
            (sum(done.what == IMPORTED for done in run.worked), "imported"),
            (sum(done.what == REFRESHED for done in run.worked), "refreshed"),
            (sum(done.what == LEFT for done in run.worked), "left as they were"),
        ),
    )


def _import_one(
    lesson: Path, importer: Importer, transcriptions: transcription.Transcriptions
) -> Done:
    note = build_note(lesson, transcribe=transcriptions.transcribe)
    done = importer.send(note)
    print(f"import: {note.code}: {_what_became_of(done, note)}")
    _report(note)
    return done


def _what_became_of(done: Done, note: Note) -> str:
    """What one lesson's import did, in the stage's own words."""
    if done.what == LEFT:
        return f"already in the collection (note {done.note_id}); left as it is"
    if done.what == REFRESHED:
        return f"refreshed note {done.note_id} in the {note.deck} deck, keeping its review history"
    return f"added note {done.note_id} to the {note.deck} deck"


def _summarize(
    command: str, run: corpus.Run, *, counts: Sequence[tuple[int, str]]
) -> int:
    """What a run over a corpus did, and which lessons it left alone.

    The per-lesson lines have already said what was done, so this says what was
    not: a corpus-wide run is one whose silences matter more than its noise. A
    count of nothing is left out rather than printed as a zero, and a run that
    worked on no lesson at all is a run that failed, and says so with its exit
    code rather than only in its summary -- one bad lesson among good ones is
    not.
    """
    parts = [
        *(f"{number} {label}" for number, label in counts if number),
        f"{len(run.skipped)} skipped",
    ]
    stopped = f", stopped at {run.stopped.lesson}" if run.stopped else ""
    count = len(run.lessons)
    lessons = "lesson" if count == 1 else "lessons"
    print(f"{command}: {count} {lessons}: {', '.join(parts)}{stopped}", file=sys.stderr)
    if run.skipped:
        print("skipped:", file=sys.stderr)
        for skip in run.skipped:
            print(f"  {skip.reason}", file=sys.stderr)
    if run.stopped:
        print(f"{command}: {run.stopped.reason}", file=sys.stderr)
        return 1
    return 0 if run.did_anything else 1


def _report(note: Note) -> None:
    """Name what the card leaves for a person, for whoever is watching.

    Both stages answer with the same report: the two are facts about the lesson,
    not about what was done with it. A word nobody transcribes is reported every
    time the lesson is built, whether it was looked for today or written into
    the file last week, because the card is the same either way.
    """
    if note.unmatched_terms:
        terms = ", ".join(note.unmatched_terms)
        print(f"{note.code}: no dialogue line carries {terms}", file=sys.stderr)
    if note.untranscribed_terms:
        words = ", ".join(note.untranscribed_terms)
        print(f"{note.code}: no transcription for {words}", file=sys.stderr)


def _report_lookups(transcriptions: transcription.Transcriptions) -> None:
    """Say what became of the words a run looked up, when it is not the usual.

    Two things a run cannot do anything about: a dictionary it could not reach,
    whose words are reported rather than quietly missing, and a file it could
    not write to, which costs the next run a lookup. The cards are made either
    way, so both are notes rather than failures.
    """
    for url, error in transcriptions.unreachable.items():
        print(
            f"transcription: {url} could not be asked ({error}); the words it "
            "would have answered are reported rather than transcribed",
            file=sys.stderr,
        )
    if transcriptions.unwritten:
        print(
            f"transcription: cannot write {transcriptions.path} "
            f"({transcriptions.unwritten}); the words this run looked up are not remembered",
            file=sys.stderr,
        )
