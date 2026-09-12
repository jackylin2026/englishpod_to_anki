"""How a word is written in phonetic symbols, and what the tool remembers about it.

The answer side of a card carries a phonetic transcription for each of its
single-word vocabulary terms, and three sources can give one: an offline
pronunciation dictionary, a free online dictionary, and Wiktionary. A lesson
built twice has to come out the same however the network behaves that day, so
what a source said is written into a file in the repository and read back from
there: a word is asked about once in the tool's lifetime -- and a build with no
network at all produces the card an earlier build with one produced.

That file is also where a person corrects the tool. It is read before any
dictionary is asked, so an entry written by hand wins over all three sources,
and a lookup never overwrites one. An entry whose value is `-` records a word no
dictionary has, so it is not asked for again -- and a build run offline uses it
the same way.

Which leaves the one thing the sources cannot settle between them: what a
service's silence means. A service that answers and has nothing to say about a
word is saying something about the word; a service that cannot be reached is
saying something about the network, and writing that down would fix a blank into
the file for good. So a miss is only remembered when every service was asked,
and a service that fails is left out of the rest of the run rather than asked
once per word.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .dictionary import core, pronunciations
from .lesson import LessonError

# Where the two online dictionaries answer, what a call may take before the
# service counts as not there at all, and what it is told about the caller --
# Wikimedia asks that a script say who it is.
DICTIONARY = "https://api.dictionaryapi.dev/api/v2/entries/en"
WIKTIONARY = "https://en.wiktionary.org/w/api.php"
TIMEOUT = 15
AGENT = "englishpod-to-anki/0.1 (https://github.com/jackylin2026/englishpod_to_anki)"

# The file the resolved transcriptions live in, beside the code that reads it.
# It is committed, and it is the file a person edits to correct a word.
FILE = Path(__file__).with_name("transcriptions.tsv")

# What is written down for a word no dictionary has. It is not a transcription
# and cannot be mistaken for one, and it means "asked; nothing has it".
NOTHING = "-"


class Unreachable(Exception):
    """A service could not be asked, so its silence says nothing about the word.

    Neither a lesson's problem nor a crash: the word is reported as one nobody
    had, nothing is written down for it, and a later run asks again.
    """


class Transcriptions:
    """The transcriptions the tool knows, and where it looks for one it does not.

    One of these is made per run and handed to the stage as a plain callable, so
    what a card is made of does not depend on there being a file, a network or a
    dictionary behind it.
    """

    def __init__(
        self,
        path: Path = FILE,
        *,
        dictionary: str = DICTIONARY,
        wiktionary: str = WIKTIONARY,
        offline: bool = False,
    ) -> None:
        self.path = path
        self.remembered = _read(path)
        self.made: dict[str, str] = {}
        # Asked in this order, and not at all when the run must not reach the
        # network: the offline dictionary is not a service and is always there.
        self.services: tuple[tuple[str, Callable[[str, str], str | None]], ...] = (
            () if offline else ((dictionary, online_dictionary), (wiktionary, online_wiktionary))
        )
        # The services that could not be asked, against the reason each gave:
        # a run that asked nobody one of its sources should say so rather than
        # leave a reader wondering why a word came back with nothing.
        self.unreachable: dict[str, str] = {}
        self.unwritten: str | None = None

    def transcribe(self, word: str) -> str:
        """One word's phonetic transcription, as `"/ˈɡɔri/"`, or `""` for none.

        Asked once per word per run: a corpus run meets the same word in a dozen
        lessons, and a lookup is the slowest thing in it.
        """
        if not word:
            return ""
        if word not in self.made:
            self.made[word] = self._resolve(word)
        return self.made[word]

    def _resolve(self, word: str) -> str:
        """What the file, the offline dictionary and the online ones know, in order."""
        if word in self.remembered:
            value = self.remembered[word]
            return "" if value == NOTHING else value
        offline = offline_transcription(word)
        if offline:
            return offline
        return self._ask(word)

    def _ask(self, word: str) -> str:
        """What the online dictionaries say, written down as soon as it is settled."""
        # Only an answer settles a word: a run asked not to reach the network
        # asked nobody, and a service that could not be reached answered nothing.
        # Both leave the word to be asked about again rather than writing a
        # silence into the file as though it were a fact about the word.
        answered = bool(self.services)
        for url, service in self.services:
            if url in self.unreachable:
                answered = False
                continue
            try:
                found = service(url, word)
            except Unreachable as error:
                # Asking the next word would be refused the same way, so this
                # service sits out the rest of the run.
                self.unreachable[url] = str(error)
                answered = False
                continue
            if found:
                self._remember(word, found)
                return found
        if answered:
            # Every service was asked and none had the word, which is a fact
            # about the word rather than about the network.
            self._remember(word, NOTHING)
        return ""

    def _remember(self, word: str, value: str) -> None:
        """Write one word's answer into the file.

        Written as it is settled rather than at the end of the run: a corpus run
        asks a few hundred questions over minutes, and a run stopped in the
        middle should not throw away what it learned.
        """
        self.remembered[word] = value
        self.unwritten = _write(self.path, self.remembered)


def offline_transcription(word: str) -> str:
    """What the offline dictionary says a word sounds like, `""` when it has no entry.

    CMUdict is a pronunciation dictionary: it answers in ARPAbet, with a stress
    digit on every vowel, and `to_ipa` writes that the way the card carries it.
    """
    entries = pronunciations().get(core(word))
    return _as_written(to_ipa(entries[0])) if entries else ""


def online_dictionary(url: str, word: str) -> str | None:
    """What the free online dictionary says about a word, `None` when it has none.

    Raises `Unreachable` when the service could not be asked at all. A word a
    dictionary has no entry for is the service answering, and is not that.
    """
    answer = _get(f"{url}/{quote(word, safe='')}")
    if not isinstance(answer, list):
        return None
    for entry in answer:
        if not isinstance(entry, dict):
            continue
        for phonetic in entry.get("phonetics") or ():
            if text := _as_written((phonetic or {}).get("text") or ""):
                return text
        if text := _as_written(entry.get("phonetic") or ""):
            return text
    return None


def online_wiktionary(url: str, word: str) -> str | None:
    """What Wiktionary says about a word, `None` when it has no transcription for it.

    Read as the page is written -- its wikitext -- because that is where the
    pronunciation templates are. An entry may carry several, a British one and
    an American one among them, and the American is the one wanted here: the
    corpus is American, and so is the card the learner built by hand.
    """
    query = urlencode(
        {
            "action": "parse",
            "page": word,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
        }
    )
    answer = _get(f"{url}?{query}")
    if not isinstance(answer, dict) or "parse" not in answer:
        return None
    return _wiktionary_transcription((answer["parse"] or {}).get("wikitext") or "")


# One `{{IPA|en|...}}` template, which is how an English pronunciation is
# written on a Wiktionary page. The arguments are what the template was called
# with, and the label saying which English one of them is among them.
IPA_TEMPLATE = re.compile(r"\{\{IPA\|en\|([^{}]*)\}\}")
AMERICAN = frozenset({"us", "ga", "genam", "general american"})

# One transcription inside an argument, brackets and all: a page may hang
# something off the transcription itself rather than pass it as an argument --
# `/ˈkæri ˌɑn/<a:US>` -- so what an argument says is found in it rather than
# being the whole of it.
TRANSCRIPTION = re.compile(r"/[^/<>]+/|\[[^\[\]<>]+\]")

# The same accent hung off a transcription, as `<a:US>` or `<a:US,Scotland>`.
AMERICAN_MARKER = re.compile(r"[<(]a[:=](US|GA|GenAm)\b", re.IGNORECASE)


def _wiktionary_transcription(wikitext: str) -> str | None:
    """The first transcription of the templates on a page, American ones first."""
    templates = [_template(inner) for inner in IPA_TEMPLATE.findall(wikitext)]
    written = [template for template in templates if template is not None]
    for preferred in (True, False):
        for american, text in written:
            if american is preferred:
                return text
    return None


def _template(inner: str) -> tuple[bool, str] | None:
    """One template's arguments, as whether it is American and what it says."""
    arguments = [argument.strip() for argument in inner.split("|")]
    text = next((found for argument in arguments if (found := _found(argument))), "")
    if not text:
        return None
    return _american(arguments), text


def _found(argument: str) -> str:
    """The transcription one argument carries, or `""` when it carries none."""
    match = TRANSCRIPTION.search(argument)
    return _as_written(match.group(0)) if match else ""


def _american(arguments: Sequence[str]) -> bool:
    """Whether a template says its transcription is the American one."""
    for argument in arguments:
        name, equals, value = argument.partition("=")
        if equals and name.strip() in ("a", "label", "q"):
            return value.strip().lower() in AMERICAN
        if AMERICAN_MARKER.search(argument):
            return True
    return False


def _get(url: str) -> Any | None:
    """One service's answer, or `None` when it answered that it has nothing.

    Everything else that goes wrong -- a service that is down, an answer that is
    not JSON, a connection that never comes up -- is `Unreachable`, since it is
    the asking that failed and not the word.
    """
    request = Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise Unreachable(f"it answered {error.code}") from error
    except (URLError, OSError, ValueError) as error:
        raise Unreachable(f"{error}") from error


# The letters the tool writes a transcription with. The three dictionaries
# spell the same sounds with different ones -- a script `ɡ` and a Latin `g`, an
# `r` and the turned one, a length mark an American card has no use for -- and a
# card that drew its words from all three would show three conventions for one
# thing. Only the letters are brought together: which vowel a dictionary heard
# is that dictionary's answer, and re-spelling a British one as an American one
# would be the tool answering instead.
HOUSE_CHARACTERS = str.maketrans(
    {"g": "ɡ", "ɹ": "r", "ɜ": "ɝ", "ː": "", "ˑ": "", "ʧ": "tʃ", "ʤ": "dʒ"}
)


def _slashed(text: str) -> str:
    """One transcription between slashes, whatever it arrived wrapped in.

    A dictionary writes it with its own slashes, or in square brackets, or as
    the symbols alone, and the three are the same transcription once the card
    has it. What a person writes in the file is read this much and no further:
    a correction is theirs, and the tool does not go over it.
    """
    text = " ".join(text.split())
    if len(text) >= 2 and text[0] in "/[" and text[-1] in "/]":
        text = text[1:-1].strip()
    return f"/{text}/" if text else ""


def _as_written(text: str) -> str:
    """What a dictionary answered, as the card carries it.

    In the house's letters, since a card drawing on three dictionaries would
    otherwise show three ways of writing the same sounds. What a person writes
    is not touched this way: see `_slashed`.
    """
    return _slashed(text.translate(HOUSE_CHARACTERS))


# The vowels, as the card writes them. A syllable's stress decides two of them:
# an unstressed `AH` is the schwa every second syllable of English has, and an
# unstressed `ER` the vowel `diaper` ends on.
VOWELS = {
    "AA": "ɑ",
    "AE": "æ",
    "AO": "ɔ",
    "AW": "aʊ",
    "AY": "aɪ",
    "EH": "ɛ",
    "EY": "eɪ",
    "IH": "ɪ",
    "IY": "i",
    "OW": "oʊ",
    "OY": "ɔɪ",
    "UH": "ʊ",
    "UW": "u",
    "AH": "ʌ",
    "ER": "ɝ",
}
UNSTRESSED = {"AH": "ə", "ER": "ɚ"}

CONSONANTS = {
    "B": "b",
    "CH": "tʃ",
    "D": "d",
    "DH": "ð",
    "F": "f",
    "G": "ɡ",
    "HH": "h",
    "JH": "dʒ",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ŋ",
    "P": "p",
    "R": "r",
    "S": "s",
    "SH": "ʃ",
    "T": "t",
    "TH": "θ",
    "V": "v",
    "W": "w",
    "Y": "j",
    "Z": "z",
    "ZH": "ʒ",
}

# A stress digit, as the mark that goes in front of the syllable carrying it.
STRESS = {"1": "ˈ", "2": "ˌ"}

# What English lets a syllable begin with. A word's consonants between two
# vowels are divided by this: a syllable starts on the longest run of them that
# could have started one, and the rest stay with the syllable before. Three is
# as long as a run gets -- `str` -- and a syllable never begins with `ŋ`.
ONSETS = frozenset(
    {
        "b", "d", "f", "ɡ", "h", "j", "k", "l", "m", "n", "p", "r", "s", "t", "v",
        "w", "z", "ð", "ʃ", "θ", "tʃ", "dʒ",
        "pl", "pr", "pj", "bl", "br", "bj", "tr", "tw", "tj", "dr", "dw", "dj",
        "kl", "kr", "kw", "kj", "ɡl", "ɡr", "ɡw", "fl", "fr", "fj", "vj", "θr",
        "θw", "ʃr", "hj", "mj", "nj", "lj", "rj", "sp", "st", "sk", "sm", "sn",
        "sl", "sw", "spl", "spr", "str", "skr", "skw", "skj", "spj", "stj",
    }
)
MAX_ONSET = 3


def to_ipa(phones: Sequence[str]) -> str:
    """One pronunciation in ARPAbet, written in the symbols the card carries.

    The stress marks are the one thing ARPAbet does not spell out: a vowel comes
    with the digit of its syllable's stress, and the mark belongs in front of the
    syllable -- in front of its onset, so `inventory` comes out `/ˌɪnvənˈtɔri/`
    rather than with the mark after the `n` the syllable before it ended on.

    The stress a word carries is left exactly as the dictionary gives it. It is
    poor on compounds -- `overstocked` comes back carrying two primary stresses
    -- and neither way of reading that (the first one wins, the last one does) is
    right often enough to be worth guessing with. The file is where a word that
    comes out wrong is put right.
    """
    written: list[str] = []
    onset: list[str] = []
    for phone in phones:
        base = phone.rstrip("012")
        stress = phone[-1] if phone[-1].isdigit() else ""
        if base not in VOWELS:
            onset.append(CONSONANTS.get(base, base.lower()))
            continue
        mark = STRESS.get(stress, "")
        # The consonants the syllable begins with are the longest run of them
        # that English lets a syllable begin with; the others are the end of the
        # syllable before, and the mark goes after them.
        began = _beginning(onset) if mark else 0
        written += [
            "".join(onset[: len(onset) - began]),
            mark,
            "".join(onset[len(onset) - began :]),
            UNSTRESSED.get(base, VOWELS[base]) if stress == "0" else VOWELS[base],
        ]
        onset = []
    return "".join(written + onset)


def _beginning(onset: Sequence[str]) -> int:
    """How many of the consonants before a vowel the syllable may begin with."""
    for length in range(min(len(onset), MAX_ONSET), 0, -1):
        if "".join(onset[len(onset) - length :]) in ONSETS:
            return length
    return 0


# The line the file opens with, which the tool writes back on every save. The
# file is the tool's and is rewritten from its entries, so this is how a person
# opening it learns what a line is.
HEADER = "# word<TAB>transcription, as the card carries it; - for a word no dictionary has\n"


def _read(path: Path) -> dict[str, str]:
    """The words already settled, and what was settled about them.

    The file is written by this tool and edited by a person, so a line that
    cannot be made sense of is reported rather than skipped: a correction
    silently ignored is worse than one the tool refuses.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise LessonError(f"cannot read {path}: {error}") from error
    settled: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        word, tab, value = line.partition("\t")
        if not tab or not word.strip():
            raise LessonError(
                f"{path} line {number} is not a word and a transcription "
                f"separated by a tab: {line!r}"
            )
        # A word written down twice is a person correcting the first line by
        # adding a second, so the later one is the one they meant.
        value = value.strip()
        settled[word.strip()] = NOTHING if value == NOTHING else _slashed(value) or NOTHING
    return settled


def _write(path: Path, settled: Mapping[str, str]) -> str | None:
    """Write every settled word back, and say why when it could not be written.

    In one order, so that what a run learned reads as a diff of the file rather
    than as the order it happened to learn it in; and beside the file it
    replaces rather than over it, so a run stopped in the middle of a write
    leaves the file it found where it was.

    Nothing here is worth failing a card over: a file that cannot be written
    costs a lookup, not a lesson, so what went wrong comes back to be reported
    once for the run instead of stopping anything.
    """
    lines = [HEADER, *(f"{word}\t{value}\n" for word, value in sorted(settled.items()))]
    beside = path.with_name(path.name + ".writing")
    try:
        beside.write_text("".join(lines), encoding="utf-8", newline="\n")
        beside.replace(path)
    except OSError as error:
        return str(error)
    return None
