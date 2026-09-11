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
    (template,) = model["cardTemplates"]
    front, back = template["Front"], template["Back"]

    assert "{{cloze:Sentences}}" in front
    # The answer side, in the design's order: the dialogue, the phonetics, the
    # glossary, the two fields kept empty, and the audio.
    order = [
        back.index("{{Phonetic symbols}}"),
        back.index("{{Words}}"),
        back.index("{{Synonym}}"),
        back.index("{{Word Family}}"),
        back.index("{{TTS}}"),
    ]
    assert order == sorted(order)
    assert back.index("{{cloze:Sentences}}") < order[0]


def test_an_existing_note_type_is_left_alone(markdown_lesson: Path, run_cli) -> None:
    anki = StubAnki(model_names=("EnglishPod Cloze",))
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
