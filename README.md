# EnglishPod to Anki

Turns a downloaded EnglishPod corpus into Anki cards for a single learner's collection.

The corpus itself stays outside this repository; the tool reads it in place.

## The three stages

Each stage is runnable on its own, against one lesson or the whole corpus.

| Stage | Does |
| --- | --- |
| `preprocess` | Reads a lesson PDF and writes a Markdown file beside it |
| `build` | Reads a lesson's Markdown and produces the note it would create, without touching Anki |
| `import` | Sends built notes to a running Anki through AnkiConnect |

The Markdown sits between extraction and card-building deliberately: it is where
an OCR error can be read and fixed once, rather than inherited by every card
built from it.

Only `preprocess` is built so far.

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

## Tests

```
.venv/bin/python -m pytest tests
```

The tests run the tool as a subprocess and assert on the Markdown it produced,
never on its internals. They need no network, no Anki and no OCR credentials.

The sample lesson they run against is drawn by
`tests/fixtures/make_sample_lesson.py`, which copies the *geometry* of a real
lesson PDF without copying any of the corpus's copyrighted text.

## Documentation

- `CONTEXT.md` — the vocabulary this project uses, and the words it avoids
- `docs/adr/` — the decisions behind the design, and what was rejected
