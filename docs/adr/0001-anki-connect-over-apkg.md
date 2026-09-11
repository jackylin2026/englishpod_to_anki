# Import through AnkiConnect, not a generated `.apkg`

Cards are written into a running Anki through the AnkiConnect add-on, rather than the tool emitting a self-contained `.apkg` file for the user to import.

The obvious alternative — building an `.apkg` with `genanki` — is more portable and needs no running Anki, and it was the initial recommendation. It was rejected because the tool is used repeatedly against an evolving corpus, and a file-based handoff leaves it blind: it cannot know which lessons are already in the collection, so it cannot skip them or refresh their content. AnkiConnect lets the tool read the collection and update a lesson's notes in place while preserving their scheduling.

The cost is a hard requirement that Anki is running with that add-on installed. For anyone who clones this repo, that is now a documented setup step.
