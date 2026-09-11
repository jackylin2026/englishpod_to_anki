"""Which strings are English words, and what one reduces to.

A word broken over a line ends in a hyphen, and so does a genuinely hyphenated
word that happens to fall at a line break. The two are identical on the page, so
the only way to tell them apart is to ask whether the word exists without its
hyphen. Deciding that, and deciding whether a dialogue carries a vocabulary
term, both begin by taking the punctuation off a word and seeing what is left.
"""

from __future__ import annotations

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
def known_words() -> frozenset[str]:
    """Every word the offline dictionary holds, read once per run.

    CMUdict is a pronunciation dictionary, and the pronunciation stage needs it
    anyway, so it does double duty here: membership is all this asks of it.
    """
    return frozenset(word.lower() for word in cmudict.words())


def core(text: str) -> str:
    """The letters of a fragment, with the punctuation around them taken off.

    This is what two words are compared by: case and the typesetter's
    punctuation say nothing about which word is meant.
    """
    return text.strip(PUNCTUATION).translate(APOSTROPHES).lower()
