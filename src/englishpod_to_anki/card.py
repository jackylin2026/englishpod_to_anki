"""The lesson card: the single note a lesson's Markdown produces.

Building is the stage that decides what a lesson looks like in Anki, so this is
where the card's design lives: the dialogue with its blanks, the glossary, the
audio it plays, and the identity a later run finds it by. It reads Markdown and
nothing else -- never a PDF -- so that a corrected Markdown is the only input
that matters.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from .dictionary import core
from .lesson import Dialogue, Lesson, LessonError, VocabularyTerm, lesson_file, read_markdown

# Every note lands in the deck the learner already keeps, and the note type is
# named so that nothing resolves Anki's built-in `Cloze` by mistake.
DECK = "EnglishPod"
NOTE_TYPE = "EnglishPod Cloze"

# One cloze number for the whole note, which is what makes it a single card.
CLOZE_NUMBER = "c1"

# The note's identity: a tag carrying the lesson code, which is the one handle
# AnkiConnect lets a note be born with (it cannot set a guid). A later run finds
# the note it made by searching for the tag.
TAG = "englishpod::"

# The six fields, in the order the card's design fixes. `Synonym` and
# `Word Family` are carried empty: the design has them, and filling them later
# should not be a schema change.
SENTENCES = "Sentences"
TTS = "TTS"
FIELDS = (SENTENCES, "Phonetic symbols", "Words", "Synonym", "Word Family", TTS)

# The dialogue breaks where the page broke: a paragraph break is a newline
# before the break, an intra-paragraph wrap a space before it.
PARAGRAPH = "\n<br>"
WRAP = " <br>"

FRONT_TEMPLATE = '<div style="text-align: left;">{{cloze:Sentences}}</div>'
# The answer side, in the design's order: the filled dialogue, the phonetic
# transcriptions, the glossary, the two fields kept empty, then the dialogue
# audio.
BACK_TEMPLATE = (
    '<div style="text-align: left;">{{cloze:Sentences}}</div><br>\n'
    '<div style="text-align: left;">{{Phonetic symbols}}</div><br>\n'
    '<div style="text-align: left;">{{Words}}</div><br>\n'
    '<div style="text-align: left;">{{Synonym}}</div><br>\n'
    '<div style="text-align: left;">{{Word Family}}</div><br>\n'
    '<div style="text-align: left;">{{TTS}}</div><br>'
)
CSS = (
    ".card {\n"
    "    font-family: arial;\n"
    "    font-size: 20px;\n"
    "    text-align: center;\n"
    "    color: black;\n"
    "    background-color: white;\n"
    "}\n"
    ".cloze {\n"
    "    font-weight: bold;\n"
    "    color: blue;\n"
    "}\n"
    ".nightMode .cloze {\n"
    "    color: lightblue;\n"
    "}\n"
)

# A bracketed annotation is a note to the reader, not part of the term: `(be)
# overstocked` is the word `overstocked`.
ANNOTATION = re.compile(r"\([^)]*\)")

# How one card's dialogue is compared against another's: a blank gives back the
# word it hides -- hint and all -- markup and line breaks become the spaces they
# stand for, and the words left are the ones compared. Punctuation goes with the
# rest of it, because the stops and apostrophes a card is written with are its
# maker's as surely as the words they blanked are.
CLOZE = re.compile(r"\{\{c\d+::(.*?)(?:::[^{}]*)?\}\}")
MARKUP = re.compile(r"<[^>]*>")
SPACE = re.compile(r"\s+")
PUNCTUATION = re.compile(r"\W+")

# A card plays its dialogue through the TTS field, which holds a reference to
# the recording as `[sound:name.mp3]`. The file is attached under the name the
# corpus gave it, so the field names the lesson's dialogue as surely as the code
# inside the PDF does -- and no two lessons were recorded into one file.
SOUND = re.compile(r"\[sound:([^\]]+)\]")

VOWELS = "aeiou"


@dataclass(frozen=True)
class Note:
    """The note one lesson produces."""

    code: str
    deck: str
    note_type: str
    tags: tuple[str, ...]
    fields: dict[str, str]
    audio: Path
    unmatched_terms: tuple[str, ...]

    def as_json(self) -> dict:
        """The note as the build stage emits it: everything import would send."""
        return {
            "lesson_code": self.code,
            "deck": self.deck,
            "note_type": self.note_type,
            "tags": list(self.tags),
            "fields": dict(self.fields),
            "audio": {"filename": self.audio.name, "path": str(self.audio)},
            "unmatched_terms": list(self.unmatched_terms),
        }


@dataclass(frozen=True)
class Blanked:
    """A dialogue with its blanks carved, and the terms that found none."""

    sentences: str
    unmatched: tuple[str, ...]
    blanks: int


def build_note(lesson_dir: Path) -> Note:
    """The note the lesson in `lesson_dir` produces, without touching Anki.

    Raises `LessonError` if the lesson cannot make the card the design calls
    for, which a lesson whose dialogue carries none of its Key Vocabulary
    cannot: a note with nothing blanked looks complete in the collection and
    asks the learner nothing.
    """
    lesson = read_markdown(lesson_file(lesson_dir, "*.md", what="Markdown"))
    audio = dialogue_audio(lesson_dir)
    blanked = blank(lesson.dialogue, lesson.key_vocabulary)
    if not blanked.blanks:
        raise LessonError(f"{lesson_dir} has no vocabulary to draw blanks from")
    return Note(
        code=lesson.code,
        deck=DECK,
        note_type=NOTE_TYPE,
        tags=(TAG + lesson.code,),
        fields={
            SENTENCES: blanked.sentences,
            "Phonetic symbols": "",
            "Words": glossary(lesson),
            "Synonym": "",
            "Word Family": "",
            TTS: f"[sound:{audio.name}]",
        },
        audio=audio,
        unmatched_terms=blanked.unmatched,
    )


def dialogue_audio(lesson_dir: Path) -> Path:
    """The lesson's dialogue recording, which the card plays.

    A lesson carries three recordings -- the dialogue, a breakdown and a review
    -- and the card plays only the dialogue. The path is absolute because Anki
    reads it in its own working directory, not the one the tool was run from.
    """
    return lesson_file(lesson_dir, "*dg.mp3", what="dialogue audio").resolve()


def plain_dialogue(field: str) -> str:
    """The words a card's dialogue field holds, whoever made the card.

    A card carries its maker's choices as well as the lesson's words: which
    terms they blanked, where they broke the lines, and how they punctuated what
    they typed. This gives back the words alone, so that a card this tool built
    and a card made by hand from the same lesson come out the same -- which is
    how a lesson the collection already holds is recognised when its note
    carries no tag to be found by.
    """
    filled = CLOZE.sub(r"\1", field)
    words = [
        PUNCTUATION.sub("", word)
        for word in SPACE.sub(" ", _unescaped(MARKUP.sub(" ", filled))).split()
    ]
    return " ".join(word for word in words if word)


def recordings(field: str) -> tuple[str, ...]:
    """The recordings a card plays, by the filenames it was given them under."""
    return tuple(SOUND.findall(field))


def _unescaped(text: str) -> str:
    """A field's text with its HTML entities resolved, as far as they go.

    Once is not always enough. A lesson whose text layer prints `&quot;` reaches
    its card as `&amp;quot;`, since the field escapes what the lesson already
    escaped; a card made by hand from the same dialogue holds the character
    itself. Both are the same words, so both are read back to them.
    """
    while (once := unescape(text)) != text:
        text = once
    return text


def design_differences(
    fields: Sequence[str], templates: Mapping[str, Mapping[str, str]]
) -> tuple[str, ...]:
    """How a note type already in the collection differs from the card's design.

    The note type is the tool's to make but not always its to trust. A field it
    lacks would be dropped from every note silently, a card side that never
    renders one would hide it, and a note type making more than one card would
    multiply every lesson. What the tool makes renders the design's fields on
    one card; anything else is reported for a person to settle.
    """
    differences: list[str] = []
    existing = {field.lower() for field in fields}
    differences += [
        f"it has no field named {field}" for field in FIELDS if field.lower() not in existing
    ]
    if len(templates) != 1:
        differences.append(f"it makes {len(templates)} cards a note, and the design makes one")
        return tuple(differences)

    (template,) = templates.values()
    sides = {side.lower(): rendered for side, rendered in template.items()}
    for side, design in (("front", FRONT_TEMPLATE), ("back", BACK_TEMPLATE)):
        missing = [
            name
            for name in _references(design)
            if name not in _references(sides.get(side, ""))
        ]
        if missing:
            differences.append(f"its {side} never renders {', '.join(missing)}")
    return tuple(differences)


def _references(template: str) -> list[str]:
    """The fields one side of a card renders, as `{{...}}` writes them.

    A conditional renders the field it names, so the marker is taken off: a
    `{{#Phonetic symbols}}` is the same field as a `{{Phonetic symbols}}`.
    """
    return [
        match.strip().lstrip("#^/").strip()
        for match in re.findall(r"\{\{([^{}]*)\}\}", template)
    ]


def blank(dialogue: Dialogue, terms: tuple[VocabularyTerm, ...]) -> Blanked:
    """The dialogue with every vocabulary term it carries blanked out.

    A term no line carries is reported rather than guessed at, so it comes back
    beside the rendered dialogue instead of in it.
    """
    tokens = _tokens(dialogue)
    keys = [core(token.text) for token in tokens]
    found: list[tuple[int, int]] = []
    unmatched: list[str] = []
    for term in terms:
        occurrences = [
            (start, start + len(form) - 1)
            for form in _forms(term.term)
            for start in _places(tokens, keys, form)
        ]
        if not occurrences:
            unmatched.append(term.term)
        found += occurrences
    return Blanked(
        sentences=_render(tokens, found), unmatched=tuple(unmatched), blanks=len(found)
    )


def glossary(lesson: Lesson) -> str:
    """Both vocabulary tables, as term, an arrow, and definition.

    Every entry appears, including the ones the dialogue never carried: this is
    where a meaning is looked up, blank or no blank.
    """
    entries = (*lesson.key_vocabulary, *lesson.supplementary_vocabulary)
    return "<br>".join(
        f"{_escaped(term.term)} -&gt; {_escaped(term.definition)}" for term in entries
    )


@dataclass(frozen=True)
class Token:
    """One word of the dialogue, where it sits, and what comes before it."""

    text: str
    separator: str
    turn: int


def _tokens(dialogue: Dialogue) -> list[Token]:
    """The dialogue's words in order, each knowing the break it follows.

    The physical lines are kept, because the card breaks where the page broke:
    a wrap inside a turn follows a space, a new turn follows a newline.
    """
    tokens: list[Token] = []
    for number, turn in enumerate(dialogue):
        for line, text in enumerate(turn):
            for position, word in enumerate(text.split()):
                separator = " "
                if not tokens:
                    separator = ""
                elif position == 0:
                    separator = PARAGRAPH if line == 0 else WRAP
                tokens.append(Token(text=word, separator=separator, turn=number))
    return tokens


def _forms(term: str) -> list[tuple[str, ...]]:
    """Every shape of the term a dialogue line may carry.

    The words themselves, and the words with any one of them inflected -- which
    is what lets `plunge` find `plunged`, `govern` find `governing`, and `road
    trip` find `road trips`. One word at a time: two at once is not an
    inflection a term takes.
    """
    words = [key for key in (core(word) for word in ANNOTATION.sub(" ", term).split()) if key]
    if not words:
        return []
    forms = [tuple(words)]
    for index, word in enumerate(words):
        forms += [
            tuple(words[:index] + [inflected] + words[index + 1 :])
            for inflected in _inflections(word)
            if inflected != word
        ]
    return forms


def _inflections(word: str) -> set[str]:
    """The simple inflections of an English word."""
    forms = {word}
    if len(word) < 3 or not word.isalpha():
        return forms
    if word.endswith("y") and word[-2] not in VOWELS:
        forms |= {word[:-1] + "ies", word[:-1] + "ied"}
    else:
        forms |= {word + "s", word + "ing"}
        if word.endswith("e"):
            # `plunge` takes a `d` and drops its `e` before the `ing`.
            forms |= {word + "d", word[:-1] + "ing"}
        else:
            forms |= {word + "ed"}
        if word.endswith(("s", "x", "z", "ch", "sh")):
            forms |= {word + "es"}
    # A short word ending consonant-vowel-consonant doubles it: stop, stopped.
    if word[-1] not in VOWELS + "wxy" and word[-2] in VOWELS and word[-3] not in VOWELS:
        forms |= {word + word[-1] + "ed", word + word[-1] + "ing"}
    return forms


def _places(tokens: list[Token], keys: list[str], form: tuple[str, ...]) -> list[int]:
    """Where a form sits in the dialogue, as the index of its first word.

    A match stays inside one turn: a term completed by the next speaker is not a
    term the dialogue carries.
    """
    length = len(form)
    return [
        start
        for start in range(len(tokens) - length + 1)
        if tokens[start].turn == tokens[start + length - 1].turn
        and keys[start : start + length] == list(form)
    ]


def _render(tokens: list[Token], occurrences: list[tuple[int, int]]) -> str:
    """The dialogue as the field it fills in, with the blanks written into it.

    One blank per occurrence, so two terms that happen to sit side by side stay
    two blanks. A term found earlier keeps an overlap it shares with a term
    found later.
    """
    owner: list[int | None] = [None] * len(tokens)
    for occurrence, (start, end) in enumerate(occurrences):
        for index in range(start, end + 1):
            if owner[index] is None:
                owner[index] = occurrence

    rendered = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        number = owner[index]
        if number is None:
            rendered += token.separator + _escaped(token.text)
            index += 1
            continue
        end = index
        while end + 1 < len(tokens) and owner[end + 1] == number:
            end += 1
        # The first word's own separator stays outside the blank, as the break
        # between it and the word before it; the ones inside are the blank's.
        hidden = _escaped(token.text) + "".join(
            other.separator + _escaped(other.text) for other in tokens[index + 1 : end + 1]
        )
        rendered += token.separator + "{{" + CLOZE_NUMBER + "::" + hidden + "}}"
        index = end + 1
    return rendered


def _escaped(text: str) -> str:
    """Text as Anki stores it: a field is HTML, so its own syntax is escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
