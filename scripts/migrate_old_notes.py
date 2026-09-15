"""Bring the collection's older EnglishPod notes onto the note type and tag the tool uses now.

This is a one-off. The notes for lessons 0006-0108 were made before the tool
named its own note type and before it tagged what it wrote, so they sit under
Anki's built-in `Cloze` model carrying no tags at all. That makes them invisible
to the tool: `import` recognises a note it has already written by its
`englishpod::<CODE>` tag before anything else, and a note without one is found
by the recording it plays or by the words of its dialogue. Bringing them onto
the `EnglishPod Cloze`
model and giving each its tag is what lets a later run find them the way it finds
every other note.

What must not move is the study schedule. These are the notes with the history --
every one of them is in the review queue, the longest intervals running into the
hundreds of days -- and a card that came back tomorrow instead of in six months
would be the whole cost of the exercise.

The note type is changed through AnkiConnect's `updateNoteModel`, which rewrites
a note's model, fields and tags and never touches its cards: the card row keeps
its identity, its due date, its interval, its reps and its ease. Both models
carry the same six fields and one cloze template, so the card is the same card
afterwards. Two things about that action shape the payload below. It takes the
note's tags wholesale rather than adding to them, so the new tag travels in the
same call. And it clears the fields and refills them by name, so all six values
have to be given back exactly as they were read -- a field left out is a field
emptied.

For a different reason the tool's own guard cannot be leaned on here. The
`EnglishPod Cloze` model and this collection's `Cloze` model both pass
`design_differences`, since the fields and the template references match (the
two differ only in `{{TTS}}` against `{{TTS }}`), so a note under the wrong type
would not be refused by the design check. Which type a note is under is therefore
asserted directly, before and after.

A lesson's code is read out of its own document, never out of a filename: the
level letter in an audio name is wrong for a large minority of the corpus
(lesson 0104's recording is `englishpod_E0104dg.mp3` and its printed code is
`C0104`), and the build directory already holds each lesson's Markdown, named
for the code inside it. The recording name is what ties one of these old notes to
its lesson, which the note's own fields do not name.

    python scripts/migrate_old_notes.py /path/to/corpus
    python scripts/migrate_old_notes.py /path/to/corpus --apply

Nothing is written until `--apply` is given. Before it writes anything it copies
the collection aside and validates the copy, and it moves one note -- the most
reviewed of them, so the schedule with the most to lose -- before the rest,
checking that note's fields, its card and its review log came through unchanged.

`--refresh` rebuilds these lessons' notes from the corpus afterwards. It is off
by default because it was measured to change nothing: every one of the 102 notes
rebuilt from the current build directory is byte-identical to what the collection
holds, in all six fields. What a networked run could still add is a phonetic
transcription for 28 words no offline dictionary has -- mostly slang and typos
(`gnarley`, `goomsman`, `housewaming`, `tmi`) that the online dictionaries are
unlikely to carry either -- and it writes whatever it learns into the committed
`transcriptions.tsv`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from englishpod_to_anki import card, cli, paths  # noqa: E402
from englishpod_to_anki.anki import DEFAULT_URL, AnkiConnect  # noqa: E402
from englishpod_to_anki.corpus import lessons  # noqa: E402
from englishpod_to_anki.importer import REPLACE, Importer  # noqa: E402
from englishpod_to_anki.lesson import LessonError, read_markdown  # noqa: E402
from englishpod_to_anki.transcription import Transcriptions  # noqa: E402

# The note type these notes are under. Anki's built-in cloze model, which this
# collection has been using for EnglishPod notes and also for seven hundred notes
# of other kinds that must not be moved -- so the model is never touched, only
# the notes that leave it.
OLD_NOTE_TYPE = "Cloze"

# Where the collection keeps a profile's files, and what the collection and its
# write-ahead log are called within one.
ANKI2 = Path.home() / ".local" / "share" / "Anki2"
COLLECTION = "collection.anki2"
BESIDE = ("collection.anki2-shm", "collection.anki2-wal")

# What a card holds that has to come through the note type change untouched.
# The card's own id and ordinal are in here because they are what says the card
# is the same card rather than one made in its place.
SCHEDULE = ("cardId", "ord", "due", "interval", "reps", "lapses", "factor", "type", "queue")

# A cloze number anywhere in a note's fields, in either of the two spellings a
# note may carry one. A number other than `c1` would make a second card when the
# note's type changes, which is a card the learner has never seen and would never
# have been given.
CLOZE = re.compile(r"\{\{c(\d+)::")

# The level letter a recording's name carries, when it carries one:
# `englishpod_E0104dg.mp3` -> `E`. Only ever used for saying where a filename
# disagrees with the code a lesson prints, never to work a code out.
LEVEL = re.compile(r"([A-Za-z])(?=\d{4})")


class Migration(AnkiConnect):
    """The collection actions this one-off needs, which making a card never does.

    The tool's own client holds only what a card is made of, so these are reached
    for here rather than added there: a stage has no use for changing a note's
    type, reading a card's review log or copying the collection aside.
    """

    def update_note_model(
        self, note_id: int, *, model: str, fields: dict[str, str], tags: Sequence[str]
    ) -> None:
        """Put a note under another type, keeping its fields and its card's schedule.

        Tags are given wholesale, not added to: leave them out and the note is
        left untagged.
        """
        self._call(
            "updateNoteModel",
            note={"id": note_id, "modelName": model, "fields": dict(fields), "tags": list(tags)},
        )

    def note_cards(self, note_ids: Sequence[int]) -> dict[int, list[dict[str, Any]]]:
        """Every card those notes have, gathered under the note each belongs to."""
        ids = [info["cards"] for info in self.notes_info(note_ids)]
        flat = [card_id for group in ids for card_id in group]
        held = {c["cardId"]: c for c in (self.cards(flat) if flat else [])}
        return {note_id: [held[i] for i in group if i in held] for note_id, group in zip(note_ids, ids)}

    def cards(self, card_ids: Sequence[int]) -> list[dict[str, Any]]:
        """What the collection holds for each of those cards."""
        return self._call("cardsInfo", cards=list(card_ids))

    def reviews(self, card_ids: Sequence[int]) -> dict[int, list[int]]:
        """Each card's reviews, as the identifiers of the review log's own rows.

        The log is what a schedule is made of: a card whose reps and interval
        survived but whose history did not is a card the learner has lost.
        """
        if not card_ids:
            return {}
        held = self._call("getReviewsOfCards", cards=list(card_ids))
        return {
            int(card_id): sorted(row["id"] for row in rows) for card_id, rows in held.items()
        }

    def active_profile(self) -> str:
        """The profile Anki has open, which is the one whose files are in use."""
        return self._call("getActiveProfile")


@dataclass(frozen=True)
class Target:
    """One old note, and everything needed to move it and to put it back."""

    note_id: int
    code: str
    lesson_dir: Path
    recording: str
    fields: dict[str, str]
    tags: list[str]
    card: dict[str, Any]
    reviews: tuple[int, ...]

    @property
    def tag(self) -> str:
        return card.TAG + self.code

    def state(self) -> dict[str, Any]:
        """What this note looked like before it was touched, for the journal."""
        return {
            "note_id": self.note_id,
            "code": self.code,
            "lesson_dir": str(self.lesson_dir),
            "recording": self.recording,
            "model": OLD_NOTE_TYPE,
            "tags": self.tags,
            "fields": self.fields,
            "card": self.card,
            "reviews": list(self.reviews),
        }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    build = paths.build_root()

    anki = Migration(args.anki_url)
    if card.NOTE_TYPE not in anki.note_types():
        print(f"the collection has no {card.NOTE_TYPE} note type; run import once first")
        return 1

    print(f"reading {args.corpus}, and the build directory {build}")
    try:
        by_recording = _codes_by_recording(args.corpus, build)
    except LessonError as error:
        print(f"the corpus is not ready: {error}")
        return 1
    print(f"  {len(by_recording)} lessons, each with a code and a dialogue recording")

    targets, unmapped = _targets(anki, by_recording)
    _say(targets, unmapped)

    for complaint in (_tag_clashes(anki, targets), _stray_cloze(targets), unmapped):
        if complaint:
            print(f"\nrefusing: {complaint}")
            return 1
    if not targets:
        print("\nnothing to migrate: no untagged notes under the old note type in this deck")
        return 0

    if not args.apply:
        print(f"\n{len(targets)} notes would move to {card.NOTE_TYPE} and be tagged. Nothing was written.")
        print("give --apply to do it.")
        return 0

    return _migrate(anki, targets, build=build, args=args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path, help="the corpus directory the lessons were built from")
    parser.add_argument(
        "--apply", action="store_true", help="do it; without this, only say what would be done"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="rebuild these notes' text from the corpus afterwards, as well as moving them",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="with --refresh, resolve transcriptions offline and reach the network not at all",
    )
    parser.add_argument(
        "--collection",
        type=Path,
        help=f"the {COLLECTION} file to copy aside (default: the open profile's)",
    )
    parser.add_argument(
        "--anki-url", default=DEFAULT_URL, help=f"where AnkiConnect listens (default {DEFAULT_URL})"
    )
    return parser


def _codes_by_recording(corpus: Path, build: Path) -> dict[str, tuple[Path, str]]:
    """Every lesson's dialogue recording, against its directory and its printed code.

    The code comes out of the lesson's Markdown, which is where the tool keeps
    what the lesson's own document printed. Two lessons claiming one recording
    name is a corpus this cannot be trusted over, so it is refused rather than
    resolved by taking the first.
    """
    found: dict[str, tuple[Path, str]] = {}
    for lesson_dir in lessons(corpus, build=build):
        code = read_markdown(paths.build_markdown(lesson_dir, build)).code
        recording = card.dialogue_audio(lesson_dir).name
        if recording in found:
            other, _ = found[recording]
            raise LessonError(f"{other} and {lesson_dir} both hold {recording}")
        found[recording] = (lesson_dir, code)
    return found


def _targets(
    anki: Migration, by_recording: dict[str, tuple[Path, str]]
) -> tuple[list[Target], list[int]]:
    """Every old note in the deck, with the lesson its recording says it is."""
    note_ids = sorted(anki.find_notes(f'deck:"{card.DECK}" note:{OLD_NOTE_TYPE} -tag:{card.TAG}*'))
    if not note_ids:
        return [], []

    infos = anki.notes_info(note_ids)
    held = anki.note_cards([info["noteId"] for info in infos if info])
    logged = anki.reviews([c["cardId"] for group in held.values() for c in group])

    targets: list[Target] = []
    unmapped: list[int] = []
    for info in infos:
        if not info:
            continue
        note_id = info["noteId"]
        names = card.recordings(_field(info, card.TTS))
        found = next((by_recording[name] for name in names if name in by_recording), None)
        if found is None:
            unmapped.append(note_id)
            continue
        lesson_dir, code = found
        cards = held.get(note_id, [])
        targets.append(
            Target(
                note_id=note_id,
                code=code,
                lesson_dir=lesson_dir,
                recording=names[0] if names else "",
                fields={name: _field(info, name) for name in card.FIELDS},
                tags=list(info.get("tags", [])),
                card={key: cards[0].get(key) for key in SCHEDULE} if cards else {},
                reviews=tuple(logged.get(cards[0]["cardId"], ())) if cards else (),
            )
        )
    return targets, unmapped


def _field(info: dict[str, Any], name: str) -> str:
    """One field of a note as the collection holds it, or nothing if it has none."""
    return info.get("fields", {}).get(name, {}).get("value", "")


def _tag_clashes(anki: Migration, targets: Sequence[Target]) -> str:
    """The complaint, if a code these notes would carry is already on another note."""
    taken = set()
    for info in anki.notes_info(sorted(anki.find_notes(f'deck:"{card.DECK}" tag:{card.TAG}*'))):
        taken.update(t[len(card.TAG) :] for t in info.get("tags", []) if t.startswith(card.TAG))
    clashes = sorted({t.code for t in targets} & taken)
    return f"{len(clashes)} of these codes are already on another note: {clashes}" if clashes else ""


def _stray_cloze(targets: Sequence[Target]) -> str:
    """The complaint, if a note carries a cloze number that would make a second card."""
    stray = sorted(
        {
            number
            for target in targets
            for value in target.fields.values()
            for number in CLOZE.findall(value)
        }
        - {"1"}
    )
    return f"some notes carry cloze numbers other than 1: c{stray}" if stray else ""


def _say(targets: Sequence[Target], unmapped: Sequence[int]) -> None:
    """Say what would be moved, and where a recording's letter disagrees with the code."""
    disagreed = 0
    for target in sorted(targets, key=lambda t: t.code):
        letter = LEVEL.search(target.recording)
        wrong = bool(letter) and letter.group(0).upper() != target.code[0].upper()
        disagreed += wrong
        print(
            f"  {target.note_id}  {target.code}  {target.recording}"
            f"{'  <- filename letter disagrees' if wrong else ''}"
        )
    print(f"\n{len(targets)} notes under {OLD_NOTE_TYPE} in the {card.DECK} deck, no tag on any of them")
    print(f"  {disagreed} whose recording's level letter is not the one the lesson prints")
    if unmapped:
        print(f"  {len(unmapped)} whose recording no lesson has: {list(unmapped)}")
    if targets:
        most = max(targets, key=lambda t: t.card.get("reps", 0))
        print(
            f"  {sum(len(t.reviews) for t in targets)} reviews to keep, and the most reviewed is "
            f"{most.note_id} ({most.code}) at {most.card.get('reps')} reps and a "
            f"{most.card.get('interval')}-day interval -- the one moved first"
        )


def _migrate(
    anki: Migration, targets: list[Target], *, build: Path, args: argparse.Namespace
) -> int:
    """Copy the collection aside, move one note, check it, then move the rest."""
    where = _where_to_keep(build)
    try:
        _back_up(anki, args.collection, where, targets=targets)
    except (OSError, sqlite3.Error) as error:
        print(f"\nrefusing: cannot make a copy of the collection to fall back on ({error})")
        return 1
    print(f"\ncopy of the collection, checked, in {where}")

    journal = where / "migrated.json"
    _write(journal, [t.state() for t in targets])
    print(f"what every note looked like, to put it back by, in {journal}")

    before = _shape(anki)
    first = max(targets, key=lambda t: t.card.get("reps", 0))
    rest = [t for t in targets if t.note_id != first.note_id]

    problems = _move(anki, first)
    if problems:
        print("\nrefusing: the first note came out wrong:\n  " + "\n  ".join(problems))
        print("nothing else was touched; the journal and the copy are untouched too")
        return 1
    print(f"\nfirst note {first.note_id} ({first.code}) moved, and its card and reviews are unchanged")

    for done, target in enumerate(rest, start=2):
        problems = _move(anki, target)
        if problems:
            print(f"  {target.note_id}: came out wrong:\n    " + "\n    ".join(problems))
        if done % 25 == 0 or done == len(targets):
            print(f"  {done} of {len(targets)} moved")

    print(f"\n{len(targets)} notes moved to {card.NOTE_TYPE}")
    bad = _verify(anki, targets)
    if bad:
        print(f"refusing to go on: {len(bad)} notes did not come out as they should: {bad}")
        return 1
    print("every note carries its tag, and every card kept its due date, interval, reps and reviews")

    _say_shape(before, _shape(anki))

    if not args.refresh:
        print("\nthe notes keep the text they had; --refresh would rebuild it from the corpus")
        return 0
    return _refresh(anki, targets, build=build, offline=args.offline)


def _move(anki: Migration, target: Target) -> tuple[str, ...]:
    """Move one note, and say what came out wrong if anything did."""
    before = _note_state(anki, target.note_id)
    anki.update_note_model(
        target.note_id, model=card.NOTE_TYPE, fields=target.fields, tags=[*target.tags, target.tag]
    )
    after = _note_state(anki, target.note_id)
    return _differences(target, before, after)


def _note_state(anki: Migration, note_id: int) -> dict[str, Any]:
    """One note's type, tags, fields, and the schedule and log of its card, as it is now."""
    infos = anki.notes_info([note_id])
    info = infos[0] if infos else {}
    cards = anki.note_cards([note_id]).get(note_id, [])
    return {
        "model": info.get("modelName", ""),
        "tags": list(info.get("tags", [])),
        "fields": {name: _field(info, name) for name in card.FIELDS},
        "card": {key: cards[0].get(key) for key in SCHEDULE} if cards else {},
        "reviews": tuple(anki.reviews([cards[0]["cardId"]]).get(cards[0]["cardId"], ())) if cards else (),
    }


def _differences(target: Target, before: dict[str, Any], after: dict[str, Any]) -> tuple[str, ...]:
    """What a note disagrees with itself about, the note type and the tag aside."""
    wrong: list[str] = []
    if after["model"] != card.NOTE_TYPE:
        wrong.append(f"its note type is {after['model']!r}, not {card.NOTE_TYPE!r}")
    if target.tag not in after["tags"]:
        wrong.append(f"it carries no {target.tag} tag")
    for name in card.FIELDS:
        if before["fields"][name] != after["fields"][name]:
            wrong.append(
                f"its {name} field went from {len(before['fields'][name])} characters to "
                f"{len(after['fields'][name])}"
            )
    for key in SCHEDULE:
        if before["card"].get(key) != after["card"].get(key):
            wrong.append(f"its card's {key} went from {before['card'].get(key)} to {after['card'].get(key)}")
    if before["reviews"] != after["reviews"]:
        wrong.append(
            f"its review log went from {len(before['reviews'])} rows to {len(after['reviews'])}"
        )
    return tuple(wrong)


def _verify(anki: Migration, targets: Sequence[Target]) -> list[int]:
    """Every note that does not now read as moved, with its schedule and its log intact."""
    bad: list[int] = []
    for target in targets:
        state = _note_state(anki, target.note_id)
        if state["model"] != card.NOTE_TYPE or target.tag not in state["tags"]:
            bad.append(target.note_id)
        elif state["fields"] != target.fields:
            bad.append(target.note_id)
        elif any(state["card"].get(key) != target.card.get(key) for key in SCHEDULE):
            bad.append(target.note_id)
        elif state["reviews"] != target.reviews:
            bad.append(target.note_id)
    return bad


def _shape(anki: Migration) -> dict[str, int]:
    """How much of the collection each search finds, for saying what moved."""
    questions = {
        "the deck": f'deck:"{card.DECK}"',
        "untagged, under the old type": f'deck:"{card.DECK}" note:{OLD_NOTE_TYPE} -tag:{card.TAG}*',
        "under the old type": f'deck:"{card.DECK}" note:{OLD_NOTE_TYPE}',
        "under the new type": f'deck:"{card.DECK}" note:"{card.NOTE_TYPE}"',
        "tagged": f'deck:"{card.DECK}" tag:{card.TAG}*',
        "the old type, collection-wide": f"note:{OLD_NOTE_TYPE}",
    }
    return {name: len(anki.find_notes(query)) for name, query in questions.items()}


def _say_shape(before: dict[str, int], after: dict[str, int]) -> None:
    """Say what changed about the collection's shape, and what deliberately did not."""
    print("")
    width = max(len(name) for name in after)
    for name, count in after.items():
        was = before.get(name)
        mark = "  (unchanged)" if was == count else f"  was {was}"
        print(f"  {name.ljust(width)}  {count}{mark}")


def _refresh(anki: Migration, targets: Sequence[Target], *, build: Path, offline: bool) -> int:
    """Rebuild these lessons' notes, which now find themselves by their tags.

    One run, not one per lesson: a word is looked up once however many lessons
    carry it, and the online dictionaries are what such a run spends its time on.
    Only the lessons behind these notes are rebuilt, so the rest of the corpus is
    left alone and a lesson the deck is missing is not quietly added.
    """
    print(f"\nrefreshing the text of {len(targets)} notes from the corpus")
    if not offline:
        print("  this asks the online dictionaries, and is the slow half")
    transcriptions = Transcriptions(offline=offline)
    importer = Importer(url=anki.url, policy=REPLACE)
    for target in sorted(targets, key=lambda t: t.code):
        cli._import_one(  # the tool's own per-lesson glue, kept private to the tool
            target.lesson_dir, build=build, importer=importer, transcriptions=transcriptions
        )
    cli._report_lookups(transcriptions)
    return 0


def _where_to_keep(build: Path) -> Path:
    """A directory of its own under the build directory, named for the moment."""
    return build / "old-notes-migration" / datetime.now().strftime("%Y-%m-%d-%H%M%S")


def _write(path: Path, held: Any) -> None:
    """Write a file in one step, so a run stopped midway leaves nothing half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    beside = path.with_name(path.name + ".writing")
    beside.write_text(json.dumps(held, indent=2, ensure_ascii=False), encoding="utf-8")
    beside.replace(path)


# The columns a card's schedule lives in, against the names AnkiConnect gives
# them: the collection's own `ivl` is what the API calls an interval.
SCHEDULE_COLUMNS = ("ord", "type", "queue", "due", "ivl", "factor", "reps", "lapses")


def _back_up(
    anki: Migration, collection: Path | None, where: Path, *, targets: Sequence[Target]
) -> Path:
    """Copy the collection aside, and check the copy before trusting it.

    The collection is a SQLite database with a write-ahead log beside it, so the
    three files are a set: copying the database alone can lose the commits the
    log still holds. Anki should be idle while this runs.

    The copy is then made to answer for itself -- but not with `PRAGMA
    integrity_check`, which cannot run here at all: a collection is indexed with
    a `unicase` collation that only Anki's own SQLite was told about, and a plain
    connection is refused. What is checked instead is the thing a fall-back is
    actually for: that the copy holds every note about to be moved, field for
    field, with the card schedule that is to be kept.
    """
    directory = (collection or _open_profile(anki)).parent
    where.mkdir(parents=True, exist_ok=True)

    source = directory / COLLECTION
    if not source.is_file():
        raise OSError(f"no {COLLECTION} in {directory}")
    shutil.copy2(source, where / COLLECTION)
    for name in BESIDE:
        beside = directory / name
        if beside.is_file():
            shutil.copy2(beside, where / name)

    copy = where / COLLECTION
    connection = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    try:
        notes = connection.execute("SELECT count(*) FROM notes").fetchone()[0]
        cards = connection.execute("SELECT count(*) FROM cards").fetchone()[0]
        wrong = _disagreements(connection, targets)
        if wrong:
            raise sqlite3.DatabaseError(
                f"the copy disagrees with the collection about {len(wrong)} things: {wrong[:5]}"
            )
    finally:
        connection.close()
    print(f"  {notes} notes and {cards} cards in it, and all {len(targets)} to be moved are there")
    return copy


def _disagreements(connection: sqlite3.Connection, targets: Sequence[Target]) -> list[str]:
    """Where the copy's own rows differ from what the journal recorded."""
    wrong: list[str] = []
    for target in targets:
        row = connection.execute("SELECT flds FROM notes WHERE id = ?", (target.note_id,)).fetchone()
        if row is None:
            wrong.append(f"{target.code} is missing")
        elif row[0].split("\x1f") != [target.fields[name] for name in card.FIELDS]:
            wrong.append(f"{target.code}'s fields read differently")

        held = connection.execute(
            f"SELECT {', '.join(SCHEDULE_COLUMNS)} FROM cards WHERE id = ?",
            (target.card.get("cardId"),),
        ).fetchone()
        if held is None:
            wrong.append(f"{target.code}'s card is missing")
            continue
        for name, value in zip(SCHEDULE_COLUMNS, held):
            key = "interval" if name == "ivl" else name
            if target.card.get(key) != value:
                wrong.append(f"{target.code}'s card {key} reads {value}, not {target.card.get(key)}")
    return wrong


def _open_profile(anki: Migration) -> Path:
    """Where the profile Anki has open keeps its collection."""
    return ANKI2 / anki.active_profile() / COLLECTION


if __name__ == "__main__":
    raise SystemExit(main())
