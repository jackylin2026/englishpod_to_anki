# EnglishPod to Anki

Turns a downloaded EnglishPod corpus into Anki cards for a single learner's collection.

The corpus itself stays outside this repository; the tool reads it in place.

## The three stages

Each stage is runnable on its own, against one lesson.

| Stage | Does |
| --- | --- |
| `preprocess` | Reads a lesson PDF and writes a Markdown file beside it |
| `build` | Reads a lesson's Markdown and produces the note it would create, without touching Anki |
| `import` | Sends built notes to a running Anki through AnkiConnect |

The Markdown sits between extraction and card-building deliberately: it is where
an OCR error can be read and fixed once, rather than inherited by every card
built from it.

Running a stage against the whole corpus in one go is still to come.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Preprocessing a lesson

Point `preprocess` at a lesson directory holding exactly one PDF:

```
englishpod-to-anki preprocess /path/to/corpus/英语博客100-150/0108
```

It writes `englishpod_D0108.md` beside `englishpod_D0108.pdf`. The file's title
line carries the lesson code read from *inside* the PDF, which in a few cases
disagrees with the filename.

An existing Markdown file is left alone, so a hand correction survives a re-run.
Pass `--force` to regenerate it after a parser fix.

Words the typesetter broke over a line are put back together, and the
distinction between those and a hyphen the author typed is settled by the
offline dictionary (`cmudict`): `immac-` / `ulate` becomes `immaculate`, while
`entry-` / `level` stays `entry-level`, because `entrylevel` is not a word. A
word the dictionary does not know keeps its hyphen rather than have one guessed
away.

## Building a card

Point `build` at a lesson directory holding its Markdown and its dialogue audio:

```
englishpod-to-anki build /path/to/corpus/英语博客100-150/0108
```

It prints the note it would create as JSON — the deck, the note type, the six
fields, the audio, and the tag that identifies it — and touches nothing. The
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
making one. The `EnglishPod Cloze` note type is created on the first import:

```
englishpod-to-anki import /path/to/corpus/英语博客100-150/0108
```

The dialogue audio is uploaded under its source filename, exactly as downloaded,
and the note is added to the deck carrying a tag of the form
`englishpod::C0108`. That tag is the note's identity, so a later run can find
the note an earlier one made. AnkiConnect is expected at `127.0.0.1:8765`; pass
`--anki-url` for somewhere else.

A lesson already in the collection is not yet detected: importing one twice is
refused by Anki as a duplicate note. Asking what to do about it — skip it, or
refresh its content and keep its review history — is the next piece of work.

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

## Documentation

- `CONTEXT.md` — the vocabulary this project uses, and the words it avoids
- `docs/adr/` — the decisions behind the design, and what was rejected
