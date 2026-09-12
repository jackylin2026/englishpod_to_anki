"""Phonetic transcriptions, tested through the command line like every stage.

The card's `Phonetic symbols` field is filled from three sources in a fixed
order -- a file in the repository, the offline dictionary, and two online ones
-- and what makes the field worth having is that the order holds: a word is
asked about once in the tool's lifetime, a hand correction outlives every
lookup, and a run with no network at all produces the card a run with one does.

The words the tests use are ones the offline dictionary does not have, so what
comes back is what a service said: `dodgy` and `undies` for the two unknown to
it, and `stockroom` and `govern` for two it knows. The services are
`tests/stub_dictionary.py`, which answers what a test lays out and keeps what it
was asked -- which is how "asked about once" is shown to be true rather than
asserted.

`tests/fixtures/corpus` holds the one lesson whose vocabulary the offline
dictionary lacks -- `newsagent`, in lesson 0001 -- which is why every run over
the corpus fixture is offline unless a test says otherwise: the fixture's own
run_cli sees to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stub_dictionary import DICTIONARY, WIKTIONARY, StubDictionary

# The words the offline dictionary has nothing for, and two it has.
DODGY = "dodgy"
UNDIES = "undies"
STOCKROOM = "stockroom"
GOVERN = "govern"
CARRY_ON = "carry-on"

# A dialogue carrying every word a table may name, since a term the dialogue
# never carries is one the card can leave unblanked but not unbuilt.
DIALOGUE = (
    "A: The whole thing was dodgy, and the undies were a bargain.\n"
    "\n"
    "B: Rules govern nothing here.\n"
    "\n"
    "A: One carry-on, no more."
)

# A stub service, at the address a run is pointed at rather than the real one.
DEAD = "http://127.0.0.1:1"


@pytest.fixture
def dictionary():
    """Stubs of the two online dictionaries, closed at the end of the test.

    A test that has words for them to answer says which; a test that has none
    gets services that answer they have nothing, which is a different thing from
    services that are not there -- see `StubDictionary.fail`.
    """
    made: list[StubDictionary] = []

    def build(
        answers: dict[str, str] | None = None, pages: dict[str, str] | None = None
    ) -> StubDictionary:
        stub = StubDictionary(answers, pages)
        made.append(stub)
        return stub

    yield build
    for stub in made:
        stub.close()


def services(stub: StubDictionary, *arguments: object) -> tuple[object, ...]:
    """The flags that point a run at a stub rather than at the real services."""
    return (
        "--dictionary-url",
        stub.url + DICTIONARY,
        "--wiktionary-url",
        stub.url + WIKTIONARY,
        *arguments,
    )


def lesson(tmp_path: Path, *terms: str, name: str = "lesson") -> Path:
    """A lesson whose Key Vocabulary is the terms a test names."""
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    rows = "".join(f"| {term} | common noun, singular | a thing |\n" for term in terms)
    (directory / "englishpod_X0001.md").write_text(
        "# X0001\n"
        "\n"
        "## Dialogue\n"
        "\n"
        f"{DIALOGUE}\n"
        "\n"
        "## Key Vocabulary\n"
        "\n"
        "| Term | Part of speech | Definition |\n"
        "| --- | --- | --- |\n"
        f"{rows}",
        encoding="utf-8",
    )
    (directory / "englishpod_X0001dg.mp3").write_bytes(b"")
    return directory


def built(lesson: Path, run_cli, *arguments: object) -> dict:
    """Build a lesson and give back the note it emitted."""
    result = run_cli("build", lesson, *arguments)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def entries(path: Path) -> list[str]:
    """The lines of the transcriptions file that are words rather than prose."""
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_a_single_word_term_is_transcribed_and_a_phrase_is_not(
    markdown_lesson: Path, dictionary, run_cli
) -> None:
    """Both tables feed the field, and a phrase feeds it nothing."""
    service = dictionary({"stockroom": "/not this one/"})
    note = built(markdown_lesson, run_cli, *services(service))

    symbols = note["fields"]["Phonetic symbols"]
    # Key Vocabulary first, then Supplementary, each word once.
    assert symbols == (
        "/ˈstɑˌkrum/<br>/ˌɪˈmækjulɪt/<br>/ˈɡʌvɚn/<br>/ˈoʊvɚˈstɑkt/"
        "<br>/ˈplʌndʒ/<br>/ˈlɛdʒɚ/<br>/ˈdrɛd/<br>/ˈkreɪt/"
    )
    assert "write off" not in symbols
    assert "open mic night" not in symbols
    assert "lay it on me" not in symbols
    # The field carries transcriptions and nothing else: no markup, no blanks.
    assert "{{" not in symbols
    assert "<span" not in symbols


def test_a_word_the_offline_dictionary_knows_is_never_asked_about(
    markdown_lesson: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    stub = dictionary()
    built(markdown_lesson, run_cli, *services(stub))

    assert stub.requests == []
    # And nothing was written down: what the offline dictionary answered is
    # never the file's business.
    assert entries(transcriptions) == []


def test_a_word_the_dictionary_lacks_is_asked_about_once_and_written_down(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})
    note = built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈdoʊdʒi/"
    assert note["untranscribed_terms"] == []
    assert stub.asked(DICTIONARY) == [DODGY]
    # The first service had it, so the second was never asked.
    assert stub.asked(WIKTIONARY) == []
    assert entries(transcriptions) == [f"{DODGY}\t/ˈdoʊdʒi/"]


def test_a_later_build_reads_the_file_and_asks_nothing(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})
    first = built(lesson(tmp_path, DODGY), run_cli, *services(stub))
    written = transcriptions.read_text(encoding="utf-8")

    # The second run is given services that are not there at all: a run that
    # needs to ask one of them cannot produce this card.
    again = built(
        lesson(tmp_path, DODGY),
        run_cli,
        "--dictionary-url",
        DEAD,
        "--wiktionary-url",
        DEAD,
    )

    assert again["fields"] == first["fields"]
    assert transcriptions.read_text(encoding="utf-8") == written


def test_a_hand_edited_entry_is_never_overwritten_by_a_lookup(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    transcriptions.write_text(f"{DODGY}\t/ˈby hand/\n", encoding="utf-8")
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})

    note = built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈby hand/"
    assert stub.requests == []
    assert entries(transcriptions) == [f"{DODGY}\t/ˈby hand/"]


def test_a_word_two_lessons_carry_is_asked_about_once(
    tmp_path: Path, dictionary, run_cli
) -> None:
    """A corpus run meets the same word in a dozen lessons; the network is slow."""
    lesson(tmp_path, DODGY, name="one")
    lesson(tmp_path, DODGY, name="two")
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})

    result = run_cli("build", tmp_path, *services(stub))

    assert result.returncode == 0, result.stderr
    assert stub.asked(DICTIONARY) == [DODGY]
    assert result.stdout.count("/ˈdoʊdʒi/") == 2


def test_the_file_is_read_before_the_offline_dictionary(
    tmp_path: Path, run_cli, transcriptions: Path
) -> None:
    """A word the offline dictionary knows is still the file's to correct."""
    transcriptions.write_text(f"{GOVERN}\t/ˈby hand/\n", encoding="utf-8")

    note = built(lesson(tmp_path, GOVERN), run_cli, "--dictionary-url", DEAD, "--wiktionary-url", DEAD)

    assert note["fields"]["Phonetic symbols"] == "/ˈby hand/"


def test_a_word_no_dictionary_has_is_left_blank_and_reported(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    """A miss is a fact about the word, and is written down as one."""
    stub = dictionary()
    built_lesson = lesson(tmp_path, DODGY)

    result = run_cli("build", built_lesson, *services(stub))

    assert result.returncode == 0, result.stderr
    note = json.loads(result.stdout)
    assert note["fields"]["Phonetic symbols"] == ""
    assert note["untranscribed_terms"] == [DODGY]
    assert DODGY in result.stderr
    # Both services were asked and neither had it, which is what `-` records.
    assert entries(transcriptions) == [f"{DODGY}\t-"]

    # A later build reports it again -- the card is the same card -- and asks
    # nobody, which is the whole point of writing the miss down.
    asked = list(stub.requests)
    again = run_cli("build", built_lesson, *services(stub))
    assert json.loads(again.stdout)["untranscribed_terms"] == [DODGY]
    assert DODGY in again.stderr
    assert stub.requests == asked


def test_an_unreachable_service_leaves_the_word_reported_and_unwritten(
    tmp_path: Path, run_cli, transcriptions: Path
) -> None:
    """A service that is not there has said nothing about the word."""
    result = run_cli(
        "build",
        lesson(tmp_path, DODGY),
        "--dictionary-url",
        DEAD,
        "--wiktionary-url",
        DEAD,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["untranscribed_terms"] == [DODGY]
    assert DODGY in result.stderr
    # Both services are the same address here, so one note covers them.
    assert result.stderr.count(f"{DEAD} could not be asked") == 1
    # Nothing is written down: a later run, when the service is back, must ask
    # the word again rather than find it settled.
    assert entries(transcriptions) == []


def test_a_service_that_will_not_answer_is_not_asked_once_per_word(
    tmp_path: Path, dictionary, run_cli
) -> None:
    stub = dictionary({DODGY: "/ˈdoʊdʒi/", UNDIES: "/ˈʌndiz/"})
    stub.fail(500)

    result = run_cli("build", lesson(tmp_path, DODGY, UNDIES), *services(stub))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["untranscribed_terms"] == [DODGY, UNDIES]
    # One ask each, not two: a service that refused the first word would refuse
    # the second the same way.
    assert stub.asked(DICTIONARY) == [DODGY]
    assert stub.asked(WIKTIONARY) == [DODGY]


def test_a_build_can_be_run_offline_only(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    stub = dictionary({DODGY: "/ˈdoʊdʒi/", STOCKROOM: "/not this one/"})

    result = run_cli(
        "build",
        lesson(tmp_path, DODGY, STOCKROOM),
        "--offline",
        "--dictionary-url",
        stub.url + DICTIONARY,
        "--wiktionary-url",
        stub.url + WIKTIONARY,
    )

    assert result.returncode == 0, result.stderr
    note = json.loads(result.stdout)
    # What the offline dictionary knows is transcribed, what it does not is
    # reported, and neither service is asked anything at all.
    assert note["fields"]["Phonetic symbols"] == "/ˈstɑˌkrum/"
    assert note["untranscribed_terms"] == [DODGY]
    assert stub.requests == []
    assert entries(transcriptions) == []


def test_an_offline_build_does_not_settle_a_word_it_could_not_ask_about(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    """A run that asked nobody must not write down that nobody had the word."""
    built_lesson = lesson(tmp_path, DODGY)

    offline = run_cli("build", built_lesson, "--offline")
    assert json.loads(offline.stdout)["untranscribed_terms"] == [DODGY]
    assert entries(transcriptions) == []

    # The word is still a word a dictionary may have, so a run that can ask
    # does ask -- and having asked, fills the field.
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})
    note = built(built_lesson, run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈdoʊdʒi/"
    assert stub.asked(DICTIONARY) == [DODGY]


def test_the_second_service_answers_when_the_first_has_nothing(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    stub = dictionary({}, {DODGY: "{{IPA|en|/ˈdɒdʒ.i/}}"})

    note = built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈdɒdʒ.i/"
    assert stub.asked(DICTIONARY) == [DODGY]
    assert stub.asked(WIKTIONARY) == [DODGY]
    assert entries(transcriptions) == [f"{DODGY}\t/ˈdɒdʒ.i/"]


def test_the_american_transcription_is_the_one_a_page_wiktionary_carries(
    tmp_path: Path, dictionary, run_cli
) -> None:
    """A page gives one English, and the corpus is American."""
    page = "{{IPA|en|/ˈdɒd͡ʒ.i/|a=UK}} {{IPA|en|/ˈdoʊdʒi/|a=US}}"
    stub = dictionary({}, {DODGY: page})

    note = built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈdoʊdʒi/"


def test_a_transcription_with_the_accent_hung_off_it_is_read_whole(
    tmp_path: Path, dictionary, run_cli
) -> None:
    """A page may write `/ˈkæri ˌɑn/<a:US>` rather than pass the accent apart."""
    page = "{{IPA|en|/ˈkæri ˌɑn/<a:US,nMmmm>|/ˈkɛri ˌɑn/<a:US,Mmmm>}}"
    stub = dictionary({}, {CARRY_ON: page})

    note = built(lesson(tmp_path, CARRY_ON), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈkæri ˌɑn/"


def test_the_tool_says_who_it_is_when_it_asks_wiktionary(
    tmp_path: Path, dictionary, run_cli
) -> None:
    """Wikimedia answers a script that does not say who it is with a refusal."""
    stub = dictionary({}, {DODGY: "{{IPA|en|/ˈdoʊdʒi/}}"})

    built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert "englishpod-to-anki" in stub.caller(WIKTIONARY)[0]


def test_the_file_is_written_in_one_order_and_keeps_what_it_held(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    transcriptions.write_text("# a header\n\nzebra\t/ˈziːbrə/\n", encoding="utf-8")
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})

    built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert entries(transcriptions) == [f"{DODGY}\t/ˈdoʊdʒi/", "zebra\t/ˈziːbrə/"]


def test_a_comment_and_a_blank_line_are_not_entries(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    """The file is written by the tool and read by a person, and both are fine."""
    transcriptions.write_text(
        "# word<TAB>transcription\n"
        "\n"
        "# the one they say in the north\n"
        f"{DODGY}\t/ˈdoʊdʒi/\n",
        encoding="utf-8",
    )
    stub = dictionary({DODGY: "/not this one/"})

    note = built(lesson(tmp_path, DODGY), run_cli, *services(stub))

    assert note["fields"]["Phonetic symbols"] == "/ˈdoʊdʒi/"
    assert stub.requests == []


def test_a_line_the_file_cannot_make_sense_of_is_reported_as_that_line(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    transcriptions.write_text(f"{DODGY} /ˈdoʊdʒi/\nGOVERN\t/ˈɡʌvɚn/\n", encoding="utf-8")
    stub = dictionary({DODGY: "/not this one/"})

    result = run_cli("build", lesson(tmp_path, DODGY), *services(stub))

    assert result.returncode == 1
    assert f"{transcriptions} line 1" in result.stderr
    assert "Traceback" not in result.stderr
    # Nothing was asked: a file the tool cannot read is read before anything
    # else happens, rather than a word at a time.
    assert stub.requests == []


def test_a_run_that_cannot_write_the_file_still_builds(
    tmp_path: Path, dictionary, run_cli, transcriptions: Path
) -> None:
    """What cannot be written down costs the next run a lookup, not this one a card."""
    stub = dictionary({DODGY: "/ˈdoʊdʒi/"})
    built_lesson = lesson(tmp_path, DODGY)
    tmp_path.chmod(0o500)
    try:
        result = run_cli("build", built_lesson, *services(stub))
    finally:
        tmp_path.chmod(0o700)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["fields"]["Phonetic symbols"] == "/ˈdoʊdʒi/"
    assert "cannot write" in result.stderr
    assert not transcriptions.exists()
