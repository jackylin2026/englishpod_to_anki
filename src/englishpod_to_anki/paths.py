"""Where the tool keeps what it writes.

The corpus is read where it lies and is not written into, so everything a stage
works out about a lesson goes to one directory of the tool's own: a Markdown, the
note it makes, and the print transcript's version of its dialogue, one lesson to a
subdirectory. The subdirectory is named for the lesson's directory in the corpus
rather than for the code inside it, because it is the one of the two the corpus
path alone says -- every lesson's directory name is its own number, so nothing
collides, and a lesson not yet preprocessed has no code to be named for anyway.

Where that directory is comes from the run rather than from the tool:
`ENGLISHPOD_BUILD_DIR` in the environment first, then the same name written in the
`.env` file the tool already reads its OCR credentials from, then a `build` under
the directory the tool was run from. The `.env` is read where the tool was run, as
the credentials are, since that is where its owner puts it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .lesson import LessonError, lesson_markdown

# The name the build directory is given in the environment and in the `.env` file
# -- the same file the OCR pass reads its credentials from, each setting carrying
# its owner's prefix so that neither can mean another tool's.
BUILD = "ENGLISHPOD_BUILD_DIR"
ENV = ".env"

# Where the tool writes when nothing says otherwise: a directory of its own
# under the directory it was run from.
DEFAULT = "build"


def settings(text: str) -> dict[str, str]:
    """A `.env` file's settings, as its `NAME=value` lines read them."""
    settings: dict[str, str] = {}
    for line in text.splitlines():
        name, equals, value = line.partition("=")
        if not equals or name.strip().startswith("#"):
            continue
        settings[name.strip()] = value.strip().strip('"').strip("'")
    return settings


def build_root(*, directory: Path | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """The directory the tool's own files are kept under.

    Set in the environment first, so that a run can be pointed somewhere for one
    invocation without touching a file; then written in the `.env`; then `build`
    under the directory the run was made from. Neither of the first two has to be
    there -- the third needs nothing said -- so a `.env` that is missing is not
    the trouble the OCR pass's missing one is.
    """
    here = directory or Path.cwd()
    where = (environ if environ is not None else os.environ).get(BUILD) or _env_setting(here / ENV, BUILD)
    return Path(where) if where else here / DEFAULT


def _env_setting(path: Path, name: str) -> str | None:
    """One setting out of the `.env` file, when there is one and it says so."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return settings(text).get(name) or None


def lesson_build(lesson_dir: Path, root: Path) -> Path:
    """The directory one lesson's own files are kept in, under the build root.

    Named for the lesson's directory rather than for the code inside it, since
    the directory is needed before the lesson has been read -- `preprocess`
    asks there for a Markdown before it opens the PDF -- and the code is only
    known once it has. A directory named by its path alone is what is left when
    a run is made from inside it, which is a name like any other once it is
    resolved.
    """
    name = lesson_dir.name or lesson_dir.resolve().name
    return root / name


def build_markdown(lesson_dir: Path, root: Path) -> Path:
    """The Markdown a lesson was preprocessed into, read out of the build directory.

    A build subdirectory holds what a lesson directory of the corpus used to: the
    lesson's own Markdown, and the print transcript's file for it beside that, told
    apart by their names. So the one is read with the same rule the other is, and
    what differs is only what there is to say when neither is there -- the stage
    that writes a Markdown is the one that would have made one.
    """
    directory = lesson_build(lesson_dir, root)
    if not directory.is_dir():
        raise LessonError(f"{lesson_dir} has no Markdown in {directory}; run preprocess on it first")
    return lesson_markdown(directory)
