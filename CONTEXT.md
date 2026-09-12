# EnglishPod to Anki

Turns a downloaded EnglishPod corpus into Anki cards for a single learner's collection.

## Language

**Corpus**:
The downloaded EnglishPod material, read where it lies and never reorganised. It carries no index of its lessons: the way it nests them is the map, and pointing a stage at the corpus directory is what runs it over all of them at once.
_Avoid_: dataset, source tree

**Lesson**:
One EnglishPod episode.
_Avoid_: episode, unit, track

**Lesson directory**:
The directory the corpus keeps one lesson in: it holds that lesson's files, and no lesson of its own. Both facts are needed, because the corpus also keeps batch directories holding ten lessons *and* a combined PDF of those ten. It holds the lesson's own Markdown, and may hold the print transcript's file for the lesson beside it.
_Avoid_: lesson folder, lesson path

**Batch directory**:
The directory the corpus nests its later lessons by the ten in. It holds lessons and the combined PDF of them, and is a container rather than a lesson: what it holds is the lessons, and the PDF beside them belongs to no one lesson.
_Avoid_: group, folder

**Ignored directory**:
A directory the corpus's owner declares out of scope in the `.englishpodignore` file at the root a stage is pointed at, by its own name or by its path from that root. Nothing about it was declined, because it is not a lesson: the walk neither looks inside it nor names it in a run.
_Avoid_: skipped directory, ignored lesson

**Lesson code**:
The identifier printed in a lesson PDF's header — a level letter and four digits, such as `C0108`. Always read from the PDF; never inferred from a filename, which disagrees with it in a small number of cases. Where a lesson has no PDF of its own, the four digits of its directory's name say which lesson to look for in the PDF beside it, and the code is still read from inside the document it is found in.
_Avoid_: lesson number, file name

**Lesson PDF**:
The per-lesson PDF holding that lesson's dialogue and vocabulary tables. Above 250 the corpus keeps an introduction sheet in its place, and the lesson's tables are in the batch's PDF one directory up.
_Avoid_: source file, transcript

**Batch PDF**:
The combined PDF a batch directory carries: one document holding the lessons of that batch — ten at most, five in the corpus's last — each beginning at the row printing its own code, and each with its dialogue and both vocabulary tables. It is the source of every lesson above 250 that has no lesson PDF of its own.
_Avoid_: ten-lesson PDF

**Introduction sheet**:
The one-page PDF the corpus keeps above 250 where a lesson's own PDF would be. It names the lesson and says what it is about, and carries no lesson code, no dialogue and no vocabulary — which is why a lesson holding one is read out of the batch's PDF instead.
_Avoid_: intro PDF, the lesson intro

**OCR pass**:
The reading of a lesson whose PDF holds no text at all — a page printed to outlines, where the text layer would have been. It renders each page, has it read by a service reached over the network and billed by the page, and gives back the same rows a text layer would have. Asked for with `--ocr` rather than being part of a run, because a run over the corpus must depend on neither the service nor its credentials nor its cost.
_Avoid_: OCR stage, scanning, image pass

**Print transcript**:
The condensed corpus-wide PDF containing dialogues for most lessons, and no vocabulary at all. It is split into one transcript file per lesson it covers, and each lesson's dialogue is checked against it.
_Avoid_: the print PDF, the condensed PDF

**Transcript file**:
The print transcript's version of one lesson's dialogue, written beside the lesson's Markdown for a lesson the print covers and holding the `## Dialogue` section and nothing else. It is not the lesson's Markdown — that is the one file in the directory the lesson's own document was read into — and it names no lesson code, so nothing reads it as a lesson.
_Avoid_: transcription file, slice, dialogue file

**Dialogue**:
A lesson's scripted conversation. Each turn opens with a speaker label — a colon after one or two words, so `A:`, `C:`, `Steven:`, `Team A:`. A name may be printed with its second word lowercase, as lesson 0117's `Airline worker:` is. There are no timestamps and no line numbers.
_Avoid_: script, transcript, conversation

**Body**:
What a speaker says in a turn, as against the speaker label that opens it — a printed row carries the label's words, if it carries any, and then the body's. A label too long for the column the labels are set in is printed over two rows, and the body begins on the first of them.
_Avoid_: text, speech

**Key Vocabulary**:
A lesson's primary vocabulary table. The only table that yields cloze blanks.
_Avoid_: vocabulary list, word list

**Supplementary Vocabulary**:
A lesson's secondary vocabulary table. Feeds the glossary only — never blanks.
_Avoid_: extra vocabulary

**Vocabulary term**:
One row of a vocabulary table: a term, a part of speech, and an English definition.
_Avoid_: word, entry, item

**Cloze blank**:
An occurrence of a Key Vocabulary term inside the dialogue, blanked out for review. Every Key Vocabulary term the dialogue contains qualifies, and every occurrence of one is blanked rather than only the first, matched across the source's line wrapping, simple inflections (`plunge` for `plunged`) and bracketed annotations (`(be) overstocked`). A term the dialogue never carries is reported, not guessed at.
_Avoid_: gap, deletion

**Glossary**:
The term-and-definition list on the answer side of a lesson card, drawn from both vocabulary tables.
_Avoid_: definitions, word list

**Phonetic transcription**:
IPA for a single-word vocabulary term. Phrases have none.
_Avoid_: pronunciation, phonetics

**Transcription file**:
The file the repository keeps the transcriptions the tool has resolved in, one word to a line, and where a word no dictionary has is written down as `-`. It is read before any dictionary is asked, which is what makes it the place a hand corrects a transcription: an entry in it is never overwritten by a lookup, and a word in it is never looked up again.
_Avoid_: cache, pronunciation file

**Dialogue audio**:
A lesson's isolated dialogue recording. The lesson's other recordings are not used.
_Avoid_: the mp3, lesson audio

**Lesson card**:
The single Anki note a lesson produces.
_Avoid_: flashcard, card set

**Card design**:
The six fields and the one card a lesson card is made of: the front rendering the dialogue, the back rendering it filled, then the phonetic transcriptions, the glossary, `Synonym`, `Word Family` and the dialogue audio. A note type in the collection that does not carry it is refused rather than written into.
_Avoid_: template, model, layout

**Note identity**:
The tag `englishpod::C0108` a note is born with, derived from its lesson code, so that a later run finds the note an earlier run made.
_Avoid_: note id, guid, key

**Existing note**:
The note the collection already holds for a lesson: one carrying the lesson's `englishpod::` tag, one playing the lesson's dialogue recording, or one whose dialogue is the lesson's own words — found in that order, the first two naming the lesson exactly and the third likening it. What is done about it — left exactly as it is, or replaced — is the learner's answer rather than the tool's.
_Avoid_: duplicate, old card

**Replace**:
Refreshing the fields of a lesson's existing note, so that the card keeps the scheduling and the review history it has earned. Never a deletion and a note made again, which would cost exactly what it is for.
_Avoid_: update, re-import, overwrite

**Skipped lesson**:
A lesson a stage declined to work on, named with the reason at the end of a run over the corpus. A lesson is skipped rather than built when it is missing its dialogue audio or its Markdown, when its PDF or Markdown cannot be read, or when it has no vocabulary to draw blanks from.
_Avoid_: failed lesson, error
