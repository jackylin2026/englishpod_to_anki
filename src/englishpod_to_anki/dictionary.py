"""The offline dictionary: which strings are English words, and how each is said.

A word broken over a line ends in a hyphen, and so does a genuinely hyphenated
word that happens to fall at a line break. The two are identical on the page, so
the only way to tell them apart is to ask whether the word exists without its
hyphen. Deciding that, and deciding whether a dialogue carries a vocabulary
term, both begin by taking the punctuation off a word and seeing what is left.

It is CMUdict, which is a pronunciation dictionary: the words it holds are the
words it can say, and the two questions are answered off one reading of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache

import cmudict

# Punctuation the typesetter hangs off a word. It says nothing about the word.
PUNCTUATION = ".,;:!?\"'’‘“”()[]{}"

# The corpus mixes the two apostrophes; the dictionary only knows one.
APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})


def is_word(text: str) -> bool:
    """Whether the dictionary knows this string as an English word."""
    return core(text) in known_words()


@lru_cache(maxsize=1)
def pronunciations() -> Mapping[str, Sequence[Sequence[str]]]:
    """Every word the offline dictionary holds, and how each of them is said.

    CMUdict groups its entries by word, since one word may be said more than one
    way, and it builds that grouping from scratch every time it is asked for it
    -- so it is asked once and kept for the rest of the run.
    """
    return cmudict.dict()


def known_words() -> frozenset[str]:
    """Every word the offline dictionary holds.

    Read off the same mapping the pronunciations come from: the words a word can
    be said to be among are the words there is something to say about.
    """
    return frozenset(pronunciations())


def core(text: str) -> str:
    """The letters of a fragment, with the punctuation around them taken off.

    This is what two words are compared by: case and the typesetter's
    punctuation say nothing about which word is meant.
    """
    return text.strip(PUNCTUATION).translate(APOSTROPHES).lower()
