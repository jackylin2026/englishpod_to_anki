"""The command line itself: one entry point, three stages runnable on their own.

Each stage has its own tests; this is only the shape of the tool, which the
stages are expected to keep as they grow.
"""

from __future__ import annotations

STAGES = ("preprocess", "build", "import")


def test_the_three_stages_are_separately_runnable(run_cli) -> None:
    listed = run_cli("--help")

    assert listed.returncode == 0
    for stage in STAGES:
        assert stage in listed.stdout
        assert run_cli(stage, "--help").returncode == 0
