"""Shared plumbing for the command-line tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parent.parent
SRC = REPOSITORY / "src"
SAMPLE_LESSON = REPOSITORY / "tests" / "fixtures" / "lesson"
SCANNED_LESSON = REPOSITORY / "tests" / "fixtures" / "scanned_lesson"


@pytest.fixture
def lesson(tmp_path: Path) -> Path:
    """A copy of the sample lesson directory, free to be written into."""
    return _copied(SAMPLE_LESSON, tmp_path)


@pytest.fixture
def scanned_lesson(tmp_path: Path) -> Path:
    """A copy of the image-only lesson directory, free to be written into."""
    return _copied(SCANNED_LESSON, tmp_path)


def _copied(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / source.name
    shutil.copytree(source, destination)
    return destination


@pytest.fixture
def run_cli():
    """Run the tool the way a user does: as a subprocess, through its command line."""

    def run(*arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "englishpod_to_anki", *(str(a) for a in arguments)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )

    return run
