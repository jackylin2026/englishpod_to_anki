# EnglishPod to Anki

Turns a downloaded EnglishPod corpus into Anki cards for a single learner's collection.

The corpus itself stays outside this repository; the tool reads it in place.

## The three stages

Each stage is runnable on its own, against one lesson or against the whole
corpus.

| Stage | Does |
| --- | --- |
| `preprocess` | Reads a lesson PDF and writes a Markdown file beside it |
| `build` | Reads a lesson's Markdown and produces the note it would create, without touching Anki |
| `import` | Sends built notes to a running Anki through AnkiConnect |

The Markdown sits between extraction and card-building deliberately: it is where
an OCR error can be read and fixed once, rather than inherited by every card
built from it.

## One lesson or the whole corpus

Point a stage at a lesson directory and it works on that lesson alone. Point it
at the corpus directory and it works through every lesson the corpus holds, in
one run:

```
englishpod-to-anki build /path/to/corpus
```

The corpus's own folder layout is the list of lessons, so there is nothing to
maintain beside it. A lesson is a directory holding a lesson's files — the
lesson PDF, its recordings, its Markdown — and a directory holding lessons of
its own is a container rather than a lesson: the corpus nests its later lessons
ten to a directory, and those directories carry a combined PDF of the ten
beside them.

A run over the corpus ends with a summary of the lessons it skipped, named with
the reason each was given:

```
preprocess: 366 lessons: 365 written, 1 skipped
skipped:
  /path/to/corpus/英语博客51-100/ENGLISHPOD主持人对话文本 holds more than one PDF: 001 - Difficult Customer.pdf, 002 - Calling In Sick.pdf, 003 - Hotel Upgrade.pdf, and 175 more
```

A lesson missing its dialogue audio, or one whose dialogue carries none of its
Key Vocabulary to blank, is skipped rather than turned into a card that looks
complete and isn't. One unreadable lesson never stops the run — but a run that
worked on no lesson at all exits non-zero, so a script cannot mistake it for
success.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Preprocessing a lesson

Point `preprocess` at a lesson directory holding exactly one PDF, or at the
corpus directory holding the lessons:

```
englishpod-to-anki preprocess /path/to/corpus/英语博客100-150/0108
englishpod-to-anki preprocess /path/to/corpus
```

It writes `englishpod_D0108.md` beside `englishpod_D0108.pdf`. The file's title
line carries the lesson code read from *inside* the PDF, which in a few cases
disagrees with the filename.

An existing Markdown file is left alone, so a hand correction survives a re-run.
Pass `--force` to regenerate it after a parser fix. A run over the corpus says
how many files it wrote and counts the ones it left as they were, rather than
repeating the way to regenerate them for every lesson.

Words the typesetter broke over a line are put back together, and the
distinction between those and a hyphen the author typed is settled by the
offline dictionary (`cmudict`): `immac-` / `ulate` becomes `immaculate`, while
`entry-` / `level` stays `entry-level`, because `entrylevel` is not a word. A
word the dictionary does not know keeps its hyphen rather than have one guessed
away.

## Building a card

Point `build` at a lesson directory holding its Markdown and its dialogue audio,
or at the corpus directory:

```
englishpod-to-anki build /path/to/corpus/英语博客100-150/0108
englishpod-to-anki build /path/to/corpus > notes.jsonl
```

It prints the note it would create as JSON — the deck, the note type, the six
fields, the audio, and the tag that identifies it — and touches nothing, one
JSON document per line for a run over the corpus. The
`Sentences` field holds the dialogue with every Key Vocabulary term it carries
blanked out; `Words` holds both vocabulary tables as `term -> definition`. The
dialogue breaks where the page broke: an intra-paragraph wrap after a space, a
paragraph break after a newline.

A term matches across the page's line wrapping, across simple inflections
(`plunge` finds `plunged`, `govern` finds `governing`) and with bracketed
annotations ignored (`(be) overstocked` is `overstocked`). A term the dialogue
never carries is listed under `unmatched_terms` and reported on stderr: the
corpus has rows like `chapter elven` for `eleven`, and those want a human eye
rather than a fuzzy match.

## Importing into Anki

Anki must be running with the
[AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed, and
the `EnglishPod` deck must already exist — the tool verifies it rather than
making one. The `EnglishPod Cloze` note type is created on the first import; if
one of that name is already there, its fields and cards are checked against the
card's design first, and import stops rather than writing notes whose glossary
or audio no card would show. Styling is yours either way — the check is about
what the card renders, not how it looks:

```
englishpod-to-anki import /path/to/corpus/英语博客100-150/0108
englishpod-to-anki import /path/to/corpus
```

The dialogue audio is uploaded under its source filename, exactly as downloaded,
and the note is added to the deck carrying a tag of the form
`englishpod::C0108`. That tag is the note's identity, so a later run can find
the note an earlier one made. AnkiConnect is expected at `127.0.0.1:8765`; pass
`--anki-url` for somewhere else.

A run over the corpus stops if the collection itself is in the way — Anki
unreachable, the deck missing, the note type not the card's design, a note
refused — and says how many notes landed before it did. Half a corpus imported
is worse than none, and a lesson the tool cannot build is not the same thing:
that one is skipped and the run carries on.

A lesson already in the collection is not yet detected, so importing one twice
stops the run: Anki refuses the second note as a duplicate. Asking what to do
about it — skip it, or refresh its content and keep its review history — is the
next piece of work.

## Tests

```
.venv/bin/python -m pytest tests
```

The tests run the tool as a subprocess and assert on what it produced — the
Markdown, the emitted note, and the requests an import makes — never on its
internals. They need no network, no Anki and no OCR credentials: `import` is
driven against `tests/stub_anki.py`, a stand-in AnkiConnect that records what it
was asked to do.

The sample lesson they run against is drawn by
`tests/fixtures/make_sample_lesson.py`, which copies the *geometry* of a real
lesson PDF without copying any of the corpus's copyrighted text. The dialogue
audio fixtures beside it are a second of silence, made with
`ffmpeg -f lavfi -i anullsrc`.

`tests/fixtures/corpus/` is a corpus laid out the way the real one is: lessons
one and two directories deep, a batch directory carrying a combined PDF of its
lessons beside them, something that is not a lesson at all, a lesson missing its
dialogue audio, and a lesson whose Markdown carries no code.

## Documentation

- `CONTEXT.md` — the vocabulary this project uses, and the words it avoids
- `docs/adr/` — the decisions behind the design, and what was rejected
