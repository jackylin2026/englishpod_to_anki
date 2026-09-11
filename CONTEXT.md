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
The directory the corpus keeps one lesson in: it holds that lesson's files, and no lesson of its own. Both facts are needed, because the corpus also keeps batch directories holding ten lessons *and* a combined PDF of those ten.
_Avoid_: lesson folder, lesson path

**Batch directory**:
The directory the corpus nests its later lessons by the ten in. It holds lessons and the combined PDF of them, and is a container rather than a lesson: what it holds is the lessons, and the PDF beside them belongs to no one lesson.
_Avoid_: group, folder

**Ignored directory**:
A directory the corpus's owner declares out of scope in the `.englishpodignore` file at the corpus root, by its own name or by its path from that root. Nothing about it was declined, because it is not a lesson: the walk neither looks inside it nor names it in a run.
_Avoid_: skipped directory, ignored lesson

**Lesson code**:
The identifier printed in a lesson PDF's header — a level letter and four digits, such as `C0108`. Always read from the PDF; never inferred from a filename, which disagrees with it in a small number of cases.
_Avoid_: lesson number, file name

**Lesson PDF**:
The per-lesson PDF holding that lesson's dialogue and vocabulary tables.
_Avoid_: source file, transcript

**Print transcript**:
The condensed corpus-wide PDF containing dialogues for most lessons, and no vocabulary at all.
_Avoid_: the print PDF, the condensed PDF

**Dialogue**:
A lesson's scripted conversation. Each turn opens with a speaker label — a colon after one or two capitalised words, so `A:`, `C:`, `Steven:`, `Team A:`. There are no timestamps and no line numbers.
_Avoid_: script, transcript, conversation

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

**Skipped lesson**:
A lesson a stage declined to work on, named with the reason at the end of a run over the corpus. A lesson is skipped rather than built when it is missing its dialogue audio or its Markdown, when its PDF or Markdown cannot be read, or when it has no vocabulary to draw blanks from.
_Avoid_: failed lesson, error
