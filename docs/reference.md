# Reference

The full behaviour of the tool: what each stage does with a corpus that is not
uniform, which lessons it skips and why, and what a run does about a lesson the
collection already holds.

New to the tool? Start with the [README](../README.md), which walks from a
fresh clone to a card in Anki. This file is what to come back to.

Every command below is `englishpod-to-anki <stage> <path>`, run with the
command on your `PATH` — see [Setup](../README.md#step-1--set-up) in the README
if it is not.

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

### Lessons with no text layer

Around seventy lessons in the corpus were printed to pictures rather than to
text, so the file holds nothing to read. An ordinary run leaves them alone and
says why:

```
preprocess: 365 lessons: 296 written, 69 skipped
skipped:
  /path/to/corpus/英语博客201-250/0239/239.pdf has no text layer; it needs the OCR pass
```

`--ocr` reads those lessons back out of their pictures and writes the same
Markdown as any other lesson, to be read and corrected the same way:

```
englishpod-to-anki preprocess /path/to/corpus/英语博客201-250/0239 --ocr
englishpod-to-anki preprocess /path/to/corpus --ocr
```

The text is read by Baidu's OCR service (通用文字识别（含位置高精度版）), which
issues a key and a secret in its console. They belong in a `.env` file in the
directory you run the tool from — `.env` is in `.gitignore`, so a key cannot be
committed by accident:

```
# .env
BAIDU_OCR_API_KEY=...
BAIDU_OCR_SECRET_KEY=...
```

The pass is separate from an ordinary run deliberately: it needs the network,
the service's key and a page-by-page bill, and none of those should stand
between you and a run over the corpus. With `--ocr`, a lesson whose PDF *does*
hold text is still read from that text — the service is only ever the answer to
a page with nothing in it — and a lesson whose Markdown is already written is
left alone, as in any other run, unless you pass `--force`.

Each page is rendered at 300 dpi and sent on its own, and what comes back is the
page's printed lines with the position of each — which is what a vocabulary
table needs, because a printed line is a cell there, and the gaps between them
are what say where one column ends and the next begins. The lines are handed to
the same reader that reads a text layer, converted into the units a text layer
is measured in, so both paths produce the same Markdown and a lesson does not
depend on which one its PDF arrived by.

If the pass reports that the service's certificate cannot be verified, that is
this machine's certificate store rather than the network — a Python installed
without a usable CA bundle. Point it at the system's own:

```
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt englishpod-to-anki preprocess /path --ocr
```

A speaker label is printed beside the first line of what that speaker says, and
a label too long for the column the labels are set in takes two rows: the
label's first half ends the row the body begins on, and the second half opens
the next row before the body carries on. The halves are one label — joined
across the break the way a word broken there is, so `Older gentle-` / `man:` is
`Older gentleman:` — and the body is read from the row the label begins on.
Lesson 0117's `Airline worker:` is printed this way, down to a lowercase second
word, so what says the halves are one label is the column they are printed in.

Words the typesetter broke over a line are put back together, and the
distinction between those and a hyphen the author typed is settled by the
offline dictionary (`cmudict`): `immac-` / `ulate` becomes `immaculate`, while
`entry-` / `level` stays `entry-level`, because `entrylevel` is not a word. A
word the dictionary does not know keeps its hyphen rather than have one guessed
away.

### Cross-checking against the print transcript

The corpus also keeps a second printing of its dialogue: the condensed print
transcript, two columns to a page, holding dialogues for most of the first 330
lessons and no vocabulary at all. Point `preprocess` at it and every lesson it
covers is checked against it:

```
englishpod-to-anki preprocess /path/to/corpus --print-transcript "/path/to/English_Pod_1-330….pdf"
```

The print's version of a lesson's dialogue is written beside the lesson's own
Markdown, as `englishpod_D0108.transcript.md` — a dialogue and nothing else, for
reading next to the lesson's file. The two are then compared, and a lesson whose
dialogue reads differently is named on stderr:

```
C0108: the print transcript's dialogue differs from the lesson's; see /path/to/corpus/英语博客100-150/0108/englishpod_D0108.transcript.md
preprocess: 365 lessons: 365 already had a Markdown file, 329 transcript files written, 32 of 329 disagreed with the print transcript, 0 skipped
```

It is a warning and nothing more. The lesson's Markdown, the file beside it and
the card built from it are the lesson's own either way, and the run carries on: a
parsing regression is something to look at rather than something the tool decides
about. A lesson the print does not cover — lessons 331 onwards, and the one its
own printing drops between 1 and 330 — is not checked, gets no file, and is not
reported.

Two dialogues are the same dialogue when the letters and digits they are made of
are the same in the same order. The print is not the lesson's own document and
its text layer is its own: it spaces, hyphenates and punctuates its lines its own
way, drops the apostrophes contractions were typed with, and prints a lesson's
code as its own printing has it (`C0003` where the lesson's document says
`B0003`, and `(D046)` for lesson 0046 — the number is what says which lesson is
meant). None of that is a disagreement; a word added, dropped or moved is. The
transcript's file for a lesson is written once and left alone after, like the
Markdown: `--force` is what asks for it again.

## Building a card

Point `build` at a lesson directory holding its Markdown and its dialogue audio,
or at the corpus directory:

```
englishpod-to-anki build /path/to/corpus/英语博客100-150/0108
englishpod-to-anki build /path/to/corpus > notes.jsonl
```

It prints the note it would create as JSON — the deck, the note type, the six
fields, the audio, and the tag that identifies it — and touches no collection
and no lesson, one JSON document per line for a run over the corpus. It does
write what it learns about words: see [Phonetic
transcriptions](#phonetic-transcriptions) below. The
`Sentences` field holds the dialogue with every Key Vocabulary term it carries
blanked out; `Words` holds both vocabulary tables as `term -> definition`. A
speaker's turn is one line, however many lines the page printed it over: what
breaks the line is a speaker changing, and that break is a blank one.

A term matches across the page's line wrapping, across simple inflections
(`plunge` finds `plunged`, `govern` finds `governing`) and with bracketed
annotations ignored (`(be) overstocked` is `overstocked`). A term the dialogue
never carries is listed under `unmatched_terms` and reported on stderr: the
corpus has rows like `chapter elven` for `eleven`, and those want a human eye
rather than a fuzzy match.

### Phonetic transcriptions

The `Phonetic symbols` field carries IPA for the lesson's single-word terms,
from both vocabulary tables, and nothing for a phrase — a term gets a
transcription wherever on the answer side it appears, and a phrase has no one
pronunciation to give. Each word is resolved once, in a fixed order: the file
below, then the offline dictionary (`cmudict`, which already settles
de-hyphenation), then the free online dictionary at `api.dictionaryapi.dev`,
then Wiktionary.

```
englishpod-to-anki build /path/to/lesson --offline
```

That file is `src/englishpod_to_anki/transcriptions.tsv`, committed with the
tool: one `word<TAB>transcription` to a line, and `-` for a word no dictionary
has. A word written in it is never looked up again, and the file is read
*before* any dictionary, so it is also where you correct a transcription — an
entry you write by hand wins over the offline dictionary too, and no lookup
overwrites one. The file is rewritten from its entries as a run learns words, so
keep comments outside it; the line it opens with says what a line is.

`--offline` keeps a build to the offline dictionary and the file and touches the
network not at all. Without it, a build asks the online dictionaries about the
words those two cannot answer, once for the whole corpus, and remembers the
answers. What it will not do is treat a service's silence as an answer: a
dictionary that cannot be reached is dropped for the rest of the run and said so
once, and the words it would have answered are left blank and reported —
`C0108: no transcription for goosebumps` — rather than written down as words
nobody has. Only a dictionary that answered "no such word" settles a word that
way. The build succeeds and the card is made either way.

`--dictionary-url` and `--wiktionary-url` point the lookups at other services,
and `--transcriptions` keeps the file somewhere other than beside the source.
`import` takes all four as `build` does: it builds the same card.

A word the offline dictionary knows is transposed from the notation it is given
in — ARPAbet, stress digits and all — into IPA, with the stress mark placed
before the syllable it falls on. Its *stress* is left as the dictionary gives
it, which is occasionally poor on compounds (`overstocked` comes out with two
primary stresses) and is what the file is for.

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

A lesson counts as already there in three ways, looked for in this order. The
deck holds a note the tool made for it — one carrying the `englishpod::C0108`
tag — and that is the note its identity names. Failing that, the deck holds a
note that plays the lesson's dialogue recording; the audio is attached under the
filename the corpus gave it, so `[sound:englishpod_D0108dg.mp3]` names the
lesson exactly, whatever the card around it says. Failing that, the deck holds a
note of *any* note type whose dialogue is the lesson's own words — which is how
cards made by hand before this tool existed are recognised when they play no
recording: their blanks, line breaks and punctuation are their maker's and their
note carries no tag, but the dialogue is the lesson's own. Replacing one of those
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
is shown to leave a card's scheduling where it found it — `preprocess --ocr`
against `tests/stub_ocr.py`, a stand-in OCR service that reads back whatever a
test says the page says, and the online dictionaries against
`tests/stub_dictionary.py`, which answers for both of them at once and keeps
every word it was asked about, which is how "looked up once" is shown rather
than asserted.

A run that builds a card is kept local by `run_cli` in `conftest.py`: it is
given a transcriptions file of its own, so no test can write into the committed
one, and it is run offline unless the test says where a dictionary answers, so
no test reaches the network by accident.

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

- [README](../README.md) — setup, and a first card built step by step
- [CONTEXT.md](../CONTEXT.md) — the vocabulary this project uses, and the words it avoids
- [docs/adr/](adr/) — the decisions behind the design, and what was rejected
