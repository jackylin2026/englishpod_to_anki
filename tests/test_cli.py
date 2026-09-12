"""The command line itself: one entry point, three stages runnable on their own.

Each stage has its own tests; this is only the shape of the tool, which the
stages are expected to keep as they grow.
"""

from __future__ import annotations

STAGES = ("preprocess", "build", "import")

# What a stage that builds a card is asked about the words on it. `preprocess`
# is not one of those: it writes Markdown, and a word's transcription is not
# part of a Markdown file.
TRANSCRIPTION_FLAGS = ("--transcriptions", "--dictionary-url", "--wiktionary-url", "--offline")


def test_the_three_stages_are_separately_runnable(run_cli) -> None:
    listed = run_cli("--help")

    assert listed.returncode == 0
    for stage in STAGES:
        assert stage in listed.stdout
        assert run_cli(stage, "--help").returncode == 0


def test_the_flags_that_say_where_a_word_is_looked_up_are_build_and_imports(
    run_cli,
) -> None:
    """The two stages that make a card, and only those, are asked about words."""
    for stage in ("build", "import"):
        helped = run_cli(stage, "--help").stdout
        for flag in TRANSCRIPTION_FLAGS:
            assert flag in helped, f"{stage} does not take {flag}"

    helped = run_cli("preprocess", "--help").stdout
    for flag in TRANSCRIPTION_FLAGS:
        assert flag not in helped
