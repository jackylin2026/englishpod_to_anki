# EnglishPod to Anki

Turns a downloaded EnglishPod corpus into Anki cards in your own collection.

You point it at the corpus you have downloaded, and it reads each lesson's PDF,
writes a Markdown file beside it, works out the note that lesson becomes, and
sends it to Anki. The corpus stays where it is — nothing in it is moved or
rewritten.

This guide goes from a fresh clone to a card you can study, one step at a time.
Once you have run it once, [the reference](docs/reference.md) has the full
behaviour for the lessons that need more care.

## The three stages

Each stage does one job, and each can run on its own — against a single lesson,
or against the whole corpus in one run.

| Stage | Reads | Does |
| --- | --- | --- |
| `preprocess` | a lesson's PDF | writes a Markdown file beside it |
| `build` | that Markdown | prints the note it would create, as JSON; Anki untouched |
| `import` | the same note | adds it to your collection through AnkiConnect |

The Markdown in the middle is the point of the design. It is where an OCR slip
or a bad line break can be read and corrected once, by hand, rather than
inherited by every card built from it.

A *lesson directory* is a directory inside the corpus holding one lesson's
files — its PDF and its recordings — such as `.../英语博客100-150/0108`. The
corpus nests its later lessons ten to a directory, so the path to a lesson can
be one directory deep or two. Every command below takes either one lesson
directory or the corpus directory holding them all.

## What you need

- **Python 3.10 or newer** (`python3 --version` to check).
- **Anki**, with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
  add-on installed — in Anki, *Tools → Add-ons → Get Add-ons*, and the code
  `2055492159`.
- **The EnglishPod corpus**, downloaded, anywhere on your disk. It stays
  outside this repository; the tool reads it where it lies.
- For the image-only lessons, a **Baidu OCR key** — see [a lesson was skipped
  because it has no text
  layer](#a-lesson-was-skipped-because-it-has-no-text-layer).

## Step 1 — Set up

```bash
git clone https://github.com/jackylin2026/englishpod_to_anki.git
cd englishpod_to_anki
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

That puts an `englishpod-to-anki` command in `.venv/bin/`, which is **not** on
your `PATH`. Either call it by its path:

```bash
.venv/bin/englishpod-to-anki --help
```

or activate the environment first and then call it by name:

```bash
source .venv/bin/activate
englishpod-to-anki --help
```

Either way you should see the three stages listed — `preprocess`, `build`,
`import`. Every command below is written in the short form, so run
`source .venv/bin/activate` once per terminal, or put `.venv/bin/` in front of
each one.

## Step 2 — Preprocess a lesson

`preprocess` reads a lesson's PDF and writes a Markdown file beside it. Start
with one lesson rather than the whole corpus, so you can see what it does:

```bash
englishpod-to-anki preprocess /path/to/corpus/英语博客100-150/0108
```

```
preprocess: wrote /path/to/corpus/英语博客100-150/0108/englishpod_D0108.md
```

Open that file. It holds the lesson's dialogue and both vocabulary tables as
plain Markdown, and it is the one place a mistake is cheap to fix: correct it
by hand now and every card built from it is right. A Markdown file that already
exists is left alone, so your corrections survive a re-run — the file is the
record of what the lesson says.

## Step 3 — Build the note, without touching Anki

`build` reads what `preprocess` wrote and prints the note that lesson would
become. It touches no collection and no lesson, which makes it the cheap way to
see what an import would do:

```bash
englishpod-to-anki build /path/to/corpus/英语博客100-150/0108
```

You get one JSON document on a single line. Abridged, it reads:

```
{"lesson_code": "C0108", "deck": "EnglishPod", "note_type": "EnglishPod Cloze",
 "tags": ["englishpod::C0108"],
 "fields": {"Sentences": "A: Morning, Ed. The auditors arrive on Monday, and I
 want the {{c1::stockroom}} {{c1::immaculate}} before they get here.\n<br>B: …",
 "Phonetic symbols": "/ˈstɑˌkrum/<br>/ˌɪˈmækjulɪt/<br>…",
 "Words": "stockroom -&gt; the room where goods are kept<br>…",
 "Synonym": "", "Word Family": "", "TTS": "[sound:englishpod_D0108dg.mp3]"},
 "audio": {…}, "unmatched_terms": […], "untranscribed_terms": []}
```

`Sentences` is the dialogue with every Key Vocabulary term blanked out, and
`Words` is the glossary — the two halves of the card. A run over the corpus
prints one line like this per lesson, so it is also what you would redirect
into a file (`> notes.jsonl`) to keep.

Two warnings may appear on the way, both on stderr, and neither one fails the
build — they are things to look at, not errors:

- `C0108: no dialogue line carries write off` — a Key Vocabulary term the
  dialogue never actually contains. A row like `chapter elven` for `eleven`
  wants a human eye, so the term is reported rather than fuzzily matched.
- `C0108: no transcription for goosebumps` — no dictionary could be reached or
  none knew the word. The card is made either way, with that one blank.

`build` may reach the network to look up phonetic transcriptions. Add
`--offline` to keep it to the dictionary that ships with the tool and the file
beside it, and to touch the network not at all:

```bash
englishpod-to-anki build /path/to/corpus/英语博客100-150/0108 --offline
```

## Step 4 — Import into Anki

Two things to do in Anki first: install **AnkiConnect** and restart Anki, then
create a deck named exactly `EnglishPod`. The tool checks the deck is there
rather than making one, so it has to exist before you import.

Then, with Anki running:

```bash
englishpod-to-anki import /path/to/corpus/英语博客100-150/0108
```

```
import: C0108: added note 1603242736000 to the EnglishPod deck
```

The `EnglishPod Cloze` note type is created on the first import, and the
dialogue audio is uploaded with it. The note carries the tag
`englishpod::C0108`, which is how a later run recognises it. Open the
`EnglishPod` deck in Anki and the card is there, ready to study.

### If the lesson is already in your collection

The tool asks rather than deciding, and nothing is written until you answer:

```
import: C0108 is already in the collection (note 1603242736000, found by its tag).
  [s]kip      leave the card, and its review history, as they are
  [r]eplace   refresh the card's content, keeping its review history
answer s or r, adding "all" to answer the same way for every lesson left:
```

Type `s` or `r`. Over more than one lesson, add `all` — `r all` — to answer the
same way for every lesson left, so a corpus-wide re-run is one decision rather
than three hundred. `--existing skip` and `--existing replace` answer ahead of
time for a run nobody is watching:

```bash
englishpod-to-anki import /path/to/corpus --existing skip
```

Neither answer deletes and remakes the note: `replace` refreshes the fields and
keeps the scheduling and review history the card has earned.

## Step 5 — Run the whole corpus

Point any stage at the corpus directory and it works through every lesson in
it, in one run:

```bash
englishpod-to-anki preprocess /path/to/corpus
englishpod-to-anki build    /path/to/corpus > notes.jsonl
englishpod-to-anki import   /path/to/corpus --existing skip
```

A run ends with a summary of what it did and which lessons it left alone. The
skipped lessons are named with the reason each was given, so nothing is quiet:

```
preprocess: 365 lessons: 296 written, 69 skipped
skipped:
  /path/to/corpus/英语博客201-250/0239/239.pdf has no text layer; it needs the OCR pass
```

Measured on the corpus the tool was built against: 296 of its 365 lessons come
out as Markdown, and the 69 left are image-only scans that want the OCR pass.
One unreadable lesson never stops the run — but a run that worked on no lesson
at all exits non-zero, so a script cannot mistake it for success.

## FAQ

### `englishpod-to-anki: command not found`

The install put the command in `.venv/bin/`, which is not on your `PATH`. Either
run `.venv/bin/englishpod-to-anki` in full, or `source .venv/bin/activate` in
this terminal first.

### How do I see what a card will look like without touching my collection?

Run `build` instead of `import` — it prints the note and writes nothing. It is
the same note `import` would send.

### A lesson was skipped. Where do I read why?

At the end of the run, under `skipped:`, one line per lesson with its reason.
Those lines go to stderr, so a command that redirects stdout to a file still
shows them in the terminal.

### A lesson was skipped because it has no text layer

Around seventy lessons in the corpus were printed to pictures rather than to
text, so their PDF holds nothing to read. That is what the OCR pass is for:

```bash
englishpod-to-anki preprocess /path/to/corpus/英语博客201-250/0239 --ocr
```

It reads the pages through Baidu's OCR service, which is billed by the page and
issues a key and a secret in its console. Put them in a `.env` file in the
directory you run the tool from:

```
BAIDU_OCR_API_KEY=...
BAIDU_OCR_SECRET_KEY=...
```

The pass is separate from an ordinary run because it needs the network, the key
and the bill — none of which should stand between you and a run over the
corpus.

### The OCR pass says the service's certificate cannot be verified

That is this machine's certificate store rather than the network — a Python
installed without a usable CA bundle. Point it at the system's own:

```bash
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt englishpod-to-anki preprocess /path --ocr
```

### `the EnglishPod deck is not in the collection; make it in Anki first`

The tool verifies the deck rather than creating one. Make a deck named exactly
`EnglishPod` in Anki — case and spelling matter — and run the import again.

### `cannot reach AnkiConnect at 127.0.0.1:8765`

Anki is not running, or the AnkiConnect add-on is not installed. Open Anki and
try again. For AnkiConnect listening somewhere else — on another machine, or on
a port you changed — pass `--anki-url`. Recent versions of the add-on also need
Anki 23.10 or newer.

### I fixed a lesson's Markdown by hand. Will the tool overwrite it?

No. `preprocess` leaves an existing Markdown file alone. Only `--force`
regenerates it — which is what you want after a parser fix, and what you must
not use afterwards, because it would undo your own corrections.

### Do I have to be online?

Only for the OCR pass and for looking up phonetic transcriptions.
`build --offline` and `import --offline` touch the network not at all, and use
the dictionary that ships with the tool plus the transcriptions already written
down in `src/englishpod_to_anki/transcriptions.tsv`.

### A word's pronunciation is wrong. Can I fix it?

Yes — add a line to `src/englishpod_to_anki/transcriptions.tsv`, one
`word<TAB>transcription` per line. The file is read before any dictionary, so
an entry you write by hand wins over them all, and it is never overwritten by a
lookup.

### The print transcript's dialogue differs from the lesson's

Pass `--print-transcript` and the run checks each lesson against the corpus's
condensed print version, writing its version beside the lesson's Markdown and
naming any lesson whose dialogue reads differently:

```bash
englishpod-to-anki preprocess /path/to/corpus --print-transcript "/path/to/English_Pod_1-330….pdf"
```

It is a warning and nothing more: the lesson's own Markdown, the file beside it
and the card built from it are the lesson's own either way. It exists so a
parsing regression gets looked at rather than passing silently.

### Something in the corpus is not a lesson, and a run trips over it

Declare the directory out of scope in a `.englishpodignore` file at the root you
point the stage at. See [directories that are not
lessons](docs/reference.md#directories-that-are-not-lessons) in the reference.

## Tests

```bash
.venv/bin/python -m pytest tests
```

They need no network, no Anki and no OCR credentials.

## Documentation

- [docs/reference.md](docs/reference.md) — the full behaviour, lesson by lesson
- [CONTEXT.md](CONTEXT.md) — the vocabulary this project uses, and the words it avoids
- [docs/adr/](docs/adr/) — the decisions behind the design, and what was rejected
