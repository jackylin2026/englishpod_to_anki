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
| `import` | Sends built notes to a running Anki through AnkiConnect, asking about the lessons already there |

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
preprocess: 365 lessons: 296 written, 69 skipped
skipped:
  /path/to/corpus/英语博客201-250/0239/239.pdf has no text layer; it needs the OCR pass
```

That is the whole corpus the tool was built against, measured from a fresh copy:
296 of its 365 lessons come out as Markdown, and the 69 left are image-only
scans that want the OCR pass — the lessons above 250 included, whose content
comes out of their batch's combined PDF. A run over a corpus that already holds
Markdown counts the new files alone. The corpus's own `.englishpodignore` names
its host-transcript directory, which is not a lesson and used to be reported as
one.

A lesson missing its dialogue audio, or one whose dialogue carries none of its
Key Vocabulary to blank, is skipped rather than turned into a card that looks
complete and isn't. One unreadable lesson never stops the run — a file that is
not a readable PDF, a PDF with no text layer, a Markdown with no lesson code —
but a run that worked on no lesson at all exits non-zero, so a script cannot
mistake it for success.

### Directories that are not lessons

A corpus holds material that belongs to no lesson, and a directory of it would
otherwise be read as one. Such a directory is *ignored* by naming it in
`.englishpodignore`, at the root you point the stage at — the run then neither
looks inside it nor reports it:

```
# /path/to/corpus/.englishpodignore

# Host transcripts: a directory of PDFs that belongs to no lesson
ENGLISHPOD主持人对话文本/

# A path from the corpus root, for a directory whose bare name is too broad
英语博客51-100/pdf-backups
```

An entry is either a directory's own name — matched wherever it sits, at any
depth — or its path from the corpus root; an absolute path that lands under the
corpus is understood as the same thing, and a `#` opens a comment line (so a
directory whose own name begins with `#` cannot be named here). Matching is
exact: no globs, no prefixes, because a pattern that over-matches takes lessons
out of every run without saying so. Three things follow from that, worth knowing
before you edit the file:

- Only the file at the directory you point the stage at is read. Pointing at one
  batch directory does not consult the corpus root's file.
- A bare name is the broad one: `0111` hides every directory called `0111`,
  wherever it sits. Use the path form to be specific.
- What an entry hides, it hides in silence: a lesson directory named there is
  simply one lesson fewer in the run, and a *batch* directory named there takes
  its ten lessons with it, and the combined PDF that would otherwise have been
  reported in their place. An entry that matches nothing changes nothing at all,
  and the directory it once named turns up in the skipped list again.
- A file the tool cannot read — bytes that are not UTF-8 — stops the run and
  says so, rather than running on without the exclusions it declares.

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

A lesson's PDF is not always the lesson's. Above lesson 250 the corpus keeps a
one-page introduction sheet where a lesson PDF would be, and keeps the lessons
themselves in the batch's combined PDF one directory up — one document holding
the batch's lessons, each beginning at the row that prints its code.
`preprocess` reads them out of it, and writes the Markdown into the lesson's own
directory, named for the code it found there (`0251/englishpod_C0251.md`). A
lesson whose number nothing beside it carries is skipped with that reason.

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

### A lesson already in your collection

Importing a lesson the collection already holds asks what to do about it rather
than deciding. Nothing is written until you answer, and neither answer
deletes and remakes the note, because the card you have already studied is what
the question exists to protect:

```
$ englishpod-to-anki import /path/to/corpus
import: C0108 is already in the collection (note 1603242736000, found by its tag).
  [s]kip      leave the card, and its review history, as they are
  [r]eplace   refresh the card's content, keeping its review history
answer s or r, adding "all" to answer the same way for every lesson left:
```

Add `all` to an answer — `s all`, `r all` — to settle every lesson left the
same way, so a corpus-wide re-run is one decision rather than three hundred.
`--existing skip` and `--existing replace` answer ahead of time, and in those
modes nothing is asked, so a scripted run never waits on a prompt it cannot
answer. A run with nobody to answer and no flag says what it was asked and what
to pass, rather than hanging on the question.

A lesson counts as already there in two ways. The deck holds a note the tool
made for it — one carrying the `englishpod::C0108` tag — and that is the note
its identity names. Failing that, the deck holds a note of *any* note type whose
dialogue is the lesson's own words, which is how cards made by hand before this
tool existed are recognised: their blanks, their line breaks and their
punctuation are their maker's and their note carries no tag, but the dialogue is
the lesson's own. Replacing one of those
writes the card's content into the note that is there, keeping its note type,
its scheduling and its review history. If that note type would not render the
card — a field it lacks, a side that hides the glossary — the lesson is reported
and left alone instead, and the run carries on.

A lesson the collection holds twice — two notes carrying one `englishpod::` tag
— is reported rather than guessed at: which of them is the lesson's note is not
the tool's to say, so both are left alone and the lesson is named in the run's
summary.

A run that left every lesson alone is a run that did its job, and exits zero —
saying how many were left as they were. A run that skipped every lesson for
reasons of its own still exits non-zero, because it did nothing.

## Tests

```
.venv/bin/python -m pytest tests
```

The tests run the tool as a subprocess and assert on what it produced — the
Markdown, the emitted note, and the requests an import makes — never on its
internals. They need no network, no Anki and no OCR credentials: `import` is
driven against `tests/stub_anki.py`, a stand-in AnkiConnect holding the notes a
test puts in it and recording what it was asked to do — which is how a replace
is shown to leave a card's scheduling where it found it.

The sample lesson they run against is drawn by
`tests/fixtures/make_sample_lesson.py`, which copies the *geometry* of a real
lesson PDF without copying any of the corpus's copyrighted text. The dialogue
audio fixtures beside it are a second of silence, made with
`ffmpeg -f lavfi -i anullsrc`.

`tests/fixtures/corpus/` is a corpus laid out the way the real one is: lessons
one and two directories deep, a batch directory carrying a combined PDF of its
ten-lesson kind beside them (drawn holding two lessons, the second beginning
mid-page under a title wrapped over two lines), the introduction sheets the
lessons above 250 keep in place of a lesson PDF, something that is not a lesson
at all, a lesson missing its dialogue audio, and a lesson whose Markdown carries
no code.

## Documentation

- `CONTEXT.md` — the vocabulary this project uses, and the words it avoids
- `docs/adr/` — the decisions behind the design, and what was rejected
