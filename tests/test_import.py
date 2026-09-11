"""Import, tested through the command line against a stub AnkiConnect.

Nothing here needs Anki: `tests/stub_anki.py` answers the actions the tool sends
and records them, so what is asserted is what the tool asked the collection to
do -- the note type it created, the media it uploaded, and the note it added to
the EnglishPod deck.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stub_anki import StubAnki, existing

FIELDS = ["Sentences", "Phonetic symbols", "Words", "Synonym", "Word Family", "TTS"]
AUDIO = "englishpod_D0108dg.mp3"

# The note the collection already holds, for the tests about a lesson already
# imported: an id older than the one `addNote` answers with, so that a test can
# tell the note a run refreshed from one it made.
EXISTING = 1603242736000

# Lesson 108 as a learner who made the card by hand before this tool existed
# would have it: a handful of the words they wanted to practise blanked, and the
# lines broken where it suited them. Same dialogue, different card -- which is
# what the tool has to see past to recognise a lesson it did not import.
HAND_BUILT = (
    "A: Morning, Ed. The auditors arrive on Monday, and I want the "
    "{{c1::stockroom}} immaculate before they get here.\n<br>"
    "Sales have {{c1::plunged}} since the spring audit.\n<br>"
    "B: I have been dreading this. Half the pallets are still unlabelled "
    "and the shutter is jammed.\n<br>"
    "A: Then get the labels printed today. Move the overflow into the "
    "{{c1::stockroom}} annex before the audit.\n<br>"
    "B: And the damaged crates? We cannot simply write off the damaged stock "
    "without a signature.\n<br>"
    "A: We are overstocked and the regulations governing compensation are new, "
    "so we book an open mic night in the annex instead."
)

# The card's design, written out here rather than read from the tool, so that
# these tests say what the card is rather than agreeing with whatever the code
# happens to do this week.
FRONT = '<div style="text-align: left;">{{cloze:Sentences}}</div>'
BACK = (
    '<div style="text-align: left;">{{cloze:Sentences}}</div><br>\n'
    '<div style="text-align: left;">{{Phonetic symbols}}</div><br>\n'
    '<div style="text-align: left;">{{Words}}</div><br>\n'
    '<div style="text-align: left;">{{Synonym}}</div><br>\n'
    '<div style="text-align: left;">{{Word Family}}</div><br>\n'
    '<div style="text-align: left;">{{TTS}}</div><br>'
)
DESIGN = {"fields": FIELDS, "templates": {"Cloze": {"Front": FRONT, "Back": BACK}}}


def design(**changes: object) -> dict:
    """The design with one thing about it changed, as a collection may hold it."""
    note_type = {"fields": list(FIELDS), "templates": {"Cloze": dict(DESIGN["templates"]["Cloze"])}}
    for name, value in changes.items():
        if name == "fields":
            note_type["fields"] = value
        elif name in ("front", "back"):
            note_type["templates"]["Cloze"][name.title()] = value
        elif name == "templates":
            note_type["templates"] = value
        else:
            raise ValueError(name)
    return note_type


def imported(
    lesson: Path, anki: StubAnki, run_cli, *arguments: object, input: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run import against the stub, the way a user points it at their own Anki.

    `input` is the answer to whatever the run asks, for the tests that leave the
    decision to the prompt.
    """
    return run_cli("import", lesson, "--anki-url", anki.url, *arguments, input=input)


def test_the_note_lands_in_the_englishpod_deck(markdown_lesson: Path, anki, run_cli) -> None:
    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 0, result.stderr
    (request,) = anki.sent("addNote")
    note = request["note"]
    assert note["deckName"] == "EnglishPod"
    assert note["modelName"] == "EnglishPod Cloze"
    assert note["fields"]["Sentences"].startswith("A: Morning, Ed.")
    assert "{{c1::stockroom}}" in note["fields"]["Sentences"]
    assert note["fields"]["TTS"] == f"[sound:{AUDIO}]"
    assert note["tags"] == ["englishpod::C0108"]


def test_the_note_type_is_created_when_the_collection_lacks_it(
    markdown_lesson: Path, anki, run_cli
) -> None:
    assert imported(markdown_lesson, anki, run_cli).returncode == 0

    (model,) = anki.sent("createModel")
    assert model["modelName"] == "EnglishPod Cloze"
    # Deliberately not Anki's own Cloze, which the hand-built card had cloned.
    assert model["modelName"] != "Cloze"
    assert model["inOrderFields"] == FIELDS
    assert model["isCloze"] is True


def test_the_note_type_carries_the_card_design(markdown_lesson: Path, anki, run_cli) -> None:
    assert imported(markdown_lesson, anki, run_cli).returncode == 0

    (model,) = anki.sent("createModel")

    assert model["cardTemplates"] == [
        {"Name": "Cloze", "Front": FRONT, "Back": BACK}
    ]


def test_an_existing_note_type_that_is_the_design_is_left_alone(
    markdown_lesson: Path, run_cli
) -> None:
    anki = StubAnki(note_types={"EnglishPod Cloze": design()})
    try:
        assert imported(markdown_lesson, anki, run_cli).returncode == 0
        assert "createModel" not in anki.actions()
        assert len(anki.sent("addNote")) == 1
    finally:
        anki.close()


def test_the_audio_is_uploaded_under_its_source_filename_before_the_note(
    markdown_lesson: Path, anki, run_cli
) -> None:
    assert imported(markdown_lesson, anki, run_cli).returncode == 0

    (media,) = anki.sent("storeMediaFile")
    assert media["filename"] == AUDIO
    # Nothing is re-encoded or renamed: the file uploaded is the corpus's own.
    assert Path(media["path"]).name == AUDIO
    assert Path(media["path"]).is_file()
    assert anki.actions().index("storeMediaFile") < anki.actions().index("addNote")


def test_a_note_type_that_hides_part_of_the_card_is_refused(
    markdown_lesson: Path, run_cli
) -> None:
    """A half-built note type would make cards with no glossary and no audio."""
    stub = StubAnki(
        note_types={
            "EnglishPod Cloze": design(
                back='<div style="text-align: left;">{{cloze:Sentences}}</div>'
            )
        },
    )
    try:
        result = imported(markdown_lesson, stub, run_cli)

        assert result.returncode == 1
        for hidden in ("Words", "TTS"):
            assert hidden in result.stderr
        assert "note type" in result.stderr
        # Nothing was written: not the media, not the note.
        assert stub.actions() == ["deckNames", "modelNames", "modelFieldNames", "modelTemplates"]
    finally:
        stub.close()


def test_a_note_type_missing_a_field_is_refused(markdown_lesson: Path, run_cli) -> None:
    """Anki drops a field the note type does not have, without saying so."""
    stub = StubAnki(
        note_types={"EnglishPod Cloze": design(fields=["Sentences", "Words", "TTS"])},
    )
    try:
        result = imported(markdown_lesson, stub, run_cli)

        assert result.returncode == 1
        assert "Phonetic symbols" in result.stderr
        assert "addNote" not in stub.actions()
    finally:
        stub.close()


def test_a_note_type_making_more_than_one_card_is_refused(
    markdown_lesson: Path, run_cli
) -> None:
    """The design is one card a lesson; two templates would double every lesson."""
    stub = StubAnki(
        note_types={
            "EnglishPod Cloze": design(
                templates={
                    "Cloze": {"Front": FRONT, "Back": BACK},
                    "Cloze (reversed)": {"Front": BACK, "Back": FRONT},
                }
            )
        },
    )
    try:
        result = imported(markdown_lesson, stub, run_cli)

        assert result.returncode == 1
        assert "2 cards" in result.stderr
        assert "addNote" not in stub.actions()
    finally:
        stub.close()


def test_a_note_type_styled_by_hand_is_still_the_design(
    markdown_lesson: Path, run_cli
) -> None:
    """How a card looks is the learner's; what it renders is the design's."""
    stub = StubAnki(
        note_types={
            "EnglishPod Cloze": design(
                back=BACK.replace("{{Words}}", "{{#Words}}{{Words}}{{/Words}}").replace(
                    "{{TTS}}", "{{FrontSide}} {{Tags}} {{TTS }}"
                )
            )
        },
    )
    try:
        assert imported(markdown_lesson, stub, run_cli).returncode == 0
        assert len(stub.sent("addNote")) == 1
    finally:
        stub.close()


def test_a_missing_deck_is_reported_rather_than_created(
    markdown_lesson: Path, run_cli
) -> None:
    anki = StubAnki(deck_names=("Default",))
    try:
        result = imported(markdown_lesson, anki, run_cli)

        assert result.returncode == 1
        assert "EnglishPod" in result.stderr
        assert "addNote" not in anki.actions()
    finally:
        anki.close()


def test_an_unreachable_anki_is_reported(markdown_lesson: Path, run_cli) -> None:
    result = run_cli("import", markdown_lesson, "--anki-url", "http://127.0.0.1:1")

    assert result.returncode == 1
    assert "Anki" in result.stderr


def test_a_refused_note_is_reported(markdown_lesson: Path, anki, run_cli) -> None:
    anki.refuse("addNote", "cannot create note because it is a duplicate")

    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 1
    assert "duplicate" in result.stderr


def test_import_names_the_terms_the_dialogue_never_carries(
    markdown_lesson: Path, anki, run_cli
) -> None:
    result = imported(markdown_lesson, anki, run_cli)

    assert "lay it on me" in result.stderr


def test_import_refuses_a_lesson_that_cannot_be_built(
    markdown_lesson: Path, anki, run_cli
) -> None:
    """A lesson missing its audio is reported, not sent half-formed."""
    (markdown_lesson / AUDIO).unlink()

    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 1
    assert "no dialogue audio" in result.stderr
    assert not anki.requests


# A lesson the collection already holds is the learner's decision rather than
# the tool's: skip it, leaving the card and its review history untouched, or
# replace it, refreshing the card's content and keeping that history. One
# answer can be given for every lesson left, and the whole question can be
# answered ahead of time with a flag, so that a scripted run never waits on a
# prompt it cannot answer.


def test_a_lesson_already_there_is_asked_about_rather_than_decided_for(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The run says which lesson it found and what can be done with it."""
    anki = stub(existing(tags=("englishpod::C0108",)))

    result = imported(markdown_lesson, anki, run_cli, input="s\n")

    assert result.returncode == 0, result.stderr
    assert "C0108 is already in the collection" in result.stdout
    assert "note 1603242736000" in result.stdout
    assert "[s]kip" in result.stdout
    assert "[r]eplace" in result.stdout
    assert "addNote" not in anki.actions()


def test_a_card_made_by_hand_is_recognised_by_the_dialogue_it_holds(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """A card the tool did not make carries no tag, so the dialogue finds it.

    The learner's collection holds cards made by hand before the tool existed,
    with the same lesson but their own choice of blanks. Importing the lesson
    again would give them a second card for it, so the lesson is recognised as
    one they already have -- whatever its card is called, and however it blanks
    the words.
    """
    anki = stub(existing(note_type="Cloze", fields={"Sentences": HAND_BUILT}))

    result = imported(markdown_lesson, anki, run_cli, input="s\n")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    assert "found by its dialogue" in result.stdout
    assert "addNote" not in anki.actions()
    assert "updateNoteFields" not in anki.actions()


def test_a_card_punctuated_its_own_way_is_still_the_lesson(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The words are the lesson's; the punctuation is the card maker's."""
    typed = HAND_BUILT.translate(str.maketrans("", "", ".,"))
    anki = stub(existing(note_type="Cloze", fields={"Sentences": typed}))

    result = imported(markdown_lesson, anki, run_cli, "--existing", "skip")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    assert "addNote" not in anki.actions()


def test_a_card_is_recognised_by_the_recording_it_plays(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The recording is the corpus's own, so the name in the field names the lesson.

    A card may be worded quite differently from the lesson's own text -- a
    hand-made one often is -- and still be that lesson's card: the dialogue
    recording it plays is the corpus's file, and no two lessons share one.
    """
    anki = stub(
        existing(
            note_type="Cloze",
            fields={"Sentences": "A: Something like that. B: Close enough.", "TTS": f"[sound:{AUDIO}]"},
        )
    )

    result = imported(markdown_lesson, anki, run_cli, input="s\n")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    assert "found by its dialogue recording" in result.stdout
    assert "addNote" not in anki.actions()


def test_a_card_playing_another_lessons_recording_is_not_this_lesson(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The recording names the lesson: somebody else's is somebody else's."""
    anki = stub(
        existing(
            note_type="Cloze",
            fields={"Sentences": "A: Something else.", "TTS": "[sound:englishpod_B0001dg.mp3]"},
        )
    )

    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 0, result.stderr
    assert len(anki.sent("addNote")) == 1


def test_a_card_that_spells_out_what_the_corpus_printed_as_an_entity_is_still_the_lesson(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """One lesson's text layer prints `&quot;`, which a card ends up escaping twice.

    A card made from the same dialogue with the character itself is not a
    different lesson because of it.
    """
    lesson = markdown_lesson / "englishpod_D0108.md"
    lesson.write_text(lesson.read_text().replace("Morning, Ed.", "Morning, &quot;Ed.&quot;"))
    anki = stub(
        existing(
            note_type="Cloze",
            fields={"Sentences": HAND_BUILT.replace("Morning, Ed.", 'Morning, "Ed."')},
        )
    )

    result = imported(markdown_lesson, anki, run_cli, "--existing", "skip")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    assert "addNote" not in anki.actions()


def test_a_note_that_vanishes_between_the_search_and_the_read_is_passed_over(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """AnkiConnect answers `{}` for a note that is gone; the run reads past it."""
    anki = stub(existing(tags=("englishpod::C0108",)), vanished=[1603242736999])

    result = imported(markdown_lesson, anki, run_cli, "--existing", "skip")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    assert "addNote" not in anki.actions()


def test_a_card_holding_another_lesson_is_not_this_lesson(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """Only the lesson's own dialogue counts: a different card is not a match."""
    anki = stub(existing(note_type="Cloze", fields={"Sentences": "A: Something else entirely."}))

    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 0, result.stderr
    assert len(anki.sent("addNote")) == 1


def test_the_dialogue_a_card_carries_may_be_blanked_and_broken_its_own_way(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """What the two cards share is the words, not the breaks or the blanks.

    A hand-made card blanks what its maker wanted to practise and breaks its
    lines where they read well; the tool blanks the lesson's whole Key
    Vocabulary. Neither difference says the lesson is not the same lesson.
    """
    anki = stub(
        existing(
            note_type="Cloze",
            fields={"Sentences": f"<div>{HAND_BUILT.replace('<br>', '<br>\n')}</div>"},
        ),
        # The learner's own note type, which renders the card the tool's does.
        note_types={"EnglishPod Cloze": design(), "Cloze": design()},
    )

    result = imported(markdown_lesson, anki, run_cli, "--existing", "replace")

    assert result.returncode == 0, result.stderr
    assert [params["note"]["id"] for params in anki.sent("updateNoteFields")] == [EXISTING]


def test_a_hand_made_card_whose_note_type_hides_the_card_is_left_alone(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """Refreshing writes the glossary into a type that may render none of it."""
    anki = stub(
        existing(note_type="Cloze", fields={"Sentences": HAND_BUILT}),
        note_types={
            "EnglishPod Cloze": design(),
            "Cloze": design(back='<div style="text-align: left;">{{cloze:Sentences}}</div>'),
        },
    )

    result = imported(markdown_lesson, anki, run_cli, "--existing", "replace")

    assert result.returncode == 1
    assert "Cloze" in result.stderr
    assert "Words" in result.stderr
    assert "updateNoteFields" not in anki.actions()


def test_a_lesson_the_collection_holds_twice_is_reported_rather_than_guessed_at(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """Two notes carrying one lesson's tag: which to refresh is not the tool's call."""
    anki = stub(
        existing(tags=("englishpod::C0108",)),
        existing(note_id=1603242736001, tags=("englishpod::C0108",)),
    )

    result = imported(markdown_lesson, anki, run_cli, "--existing", "replace")

    assert result.returncode == 1
    assert "englishpod::C0108" in result.stderr
    assert "updateNoteFields" not in anki.actions()
    assert "addNote" not in anki.actions()


def test_a_prompt_nobody_answers_is_reported_rather_than_waited_on(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """A run with no one at the keyboard must not hang on the question."""
    anki = stub(existing(tags=("englishpod::C0108",)))

    result = imported(markdown_lesson, anki, run_cli)

    assert result.returncode == 1
    assert "already in the collection" in result.stderr
    assert "--existing" in result.stderr
    assert "addNote" not in anki.actions()


def test_the_prompt_takes_replace_as_an_answer(markdown_lesson: Path, stub, run_cli) -> None:
    """Answered at the keyboard, replace refreshes the note the same way."""
    anki = stub(existing(tags=("englishpod::C0108",)))

    result = imported(markdown_lesson, anki, run_cli, input="r\n")

    assert result.returncode == 0, result.stderr
    assert [params["note"]["id"] for params in anki.sent("updateNoteFields")] == [EXISTING]
    assert "addNote" not in anki.actions()


def test_an_answer_that_is_neither_says_so_and_asks_again(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """A mistyped answer leaves the note alone rather than being read as one."""
    anki = stub(existing(tags=("englishpod::C0108",)))

    result = imported(markdown_lesson, anki, run_cli, input="\nwhat?\ns\n")

    assert result.returncode == 0, result.stderr
    assert "'what?' is not one of the answers" in result.stdout
    # The last answer was the one acted on: skip, so nothing was written.
    assert "addNote" not in anki.actions()
    assert "updateNoteFields" not in anki.actions()


def test_replacing_refreshes_the_note_that_is_there(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The content is rebuilt; the note it lands on is the one already there."""
    anki = stub(
        existing(tags=("englishpod::C0108",), fields=dict.fromkeys(FIELDS, "what it held before"))
    )

    result = imported(markdown_lesson, anki, run_cli, "--existing", "replace")

    assert result.returncode == 0, result.stderr
    (update,) = anki.sent("updateNoteFields")
    assert update["note"]["id"] == EXISTING
    fields = update["note"]["fields"]
    assert fields["Sentences"].startswith("A: Morning, Ed.")
    assert "{{c1::stockroom}}" in fields["Sentences"]
    assert fields["TTS"] == f"[sound:{AUDIO}]"
    assert "addNote" not in anki.actions()


def test_replacing_keeps_the_card_that_note_had_already_made(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """Deleting the note and making it again would throw the review history away."""
    anki = stub(existing(tags=("englishpod::C0108",)))
    scheduling = dict(anki.note(EXISTING)["card"])

    result = imported(markdown_lesson, anki, run_cli, "--existing", "replace")

    assert result.returncode == 0, result.stderr
    assert "addNote" not in anki.actions()
    assert "deleteNotes" not in anki.actions()
    assert anki.note(EXISTING)["card"] == scheduling
    # The note is refreshed in the deck it is already in, and keeps its tag.
    assert anki.note(EXISTING)["deck"] == "EnglishPod"
    assert anki.note(EXISTING)["tags"] == ["englishpod::C0108"]


def test_skipping_leaves_a_lesson_already_there_untouched(
    markdown_lesson: Path, stub, run_cli
) -> None:
    """The card the collection holds is neither written to nor added to."""
    anki = stub(existing(tags=("englishpod::C0108",)))

    result = imported(markdown_lesson, anki, run_cli, "--existing", "skip")

    assert result.returncode == 0, result.stderr
    assert "already in the collection" in result.stdout
    # Answered by the flag, so the run never asked.
    assert "[s]kip" not in result.stdout
    assert "addNote" not in anki.actions()
    assert "updateNoteFields" not in anki.actions()
