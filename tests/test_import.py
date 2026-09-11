"""Import, tested through the command line against a stub AnkiConnect.

Nothing here needs Anki: `tests/stub_anki.py` answers the actions the tool sends
and records them, so what is asserted is what the tool asked the collection to
do -- the note type it created, the media it uploaded, and the note it added to
the EnglishPod deck.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from stub_anki import StubAnki

FIELDS = ["Sentences", "Phonetic symbols", "Words", "Synonym", "Word Family", "TTS"]
AUDIO = "englishpod_D0108dg.mp3"

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
    lesson: Path, anki: StubAnki, run_cli, *arguments: object
) -> subprocess.CompletedProcess[str]:
    """Run import against the stub, the way a user points it at their own Anki."""
    return run_cli("import", lesson, "--anki-url", anki.url, *arguments)


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
    anki = StubAnki(model_names=("EnglishPod Cloze",), note_type=design())
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
        model_names=("EnglishPod Cloze",),
        note_type=design(back='<div style="text-align: left;">{{cloze:Sentences}}</div>'),
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
        model_names=("EnglishPod Cloze",),
        note_type=design(fields=["Sentences", "Words", "TTS"]),
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
        model_names=("EnglishPod Cloze",),
        note_type=design(
            templates={
                "Cloze": {"Front": FRONT, "Back": BACK},
                "Cloze (reversed)": {"Front": BACK, "Back": FRONT},
            }
        ),
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
        model_names=("EnglishPod Cloze",),
        note_type=design(
            back=BACK.replace(
                "{{Words}}", "{{#Words}}{{Words}}{{/Words}}"
            ).replace("{{TTS}}", "{{FrontSide}} {{Tags}} {{TTS }}")
        ),
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
