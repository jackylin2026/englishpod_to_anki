"""Reading a lesson out of a page that holds no text at all.

Around seventy lessons in the corpus were printed to pictures rather than to
text: the page is all outlines, and nothing in the file says what it holds.
Preprocess cannot read one -- it says so, and names it -- which is what this
pass is for. It is a separate pass rather than a step of an ordinary run,
because it reaches a service over the network and costs money to call, and a
run over a corpus should need neither.

The service is Baidu's 通用文字识别（含位置高精度版）, spoken to over its own
REST API: a key and a secret are traded for a token, and one page at a time is
posted as a picture against that token. Both values are read from a `.env` file
rather than from the source or anything else committed, so the tool can carry no
secret, and a missing one is a sentence to act on rather than a stack trace.

What comes back is lines of text with coordinates -- the same thing the text
layer would have given -- so a page read this way arrives at the same rows as a
page read out of the text layer, and the lesson above them is read by the same
code. One line is a printed line of the page, and on a vocabulary page a printed
line is a cell: the term, the part of speech and the definition are three lines
side by side, which is what lets the columns be found by the same geometry that
finds them in a text layer.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pdfplumber

from .paths import ENV, settings
from pdfplumber.utils.exceptions import PdfminerException

from .layout import Row, Seen, page_rows
from .lesson import LessonError

# Where the service answers, and the two endpoints spoken to.
BASE = "https://aip.baidubce.com"
TOKEN = "/oauth/2.0/token"
READ = "/rest/2.0/ocr/v1/accurate"

# The two values the OCR pass needs out of the `.env` file, which is the same one
# the build directory is read from.
API_KEY = "BAIDU_OCR_API_KEY"
SECRET_KEY = "BAIDU_OCR_SECRET_KEY"

# A page is rendered at 300 dpi before it is sent: fine enough for the small
# print of a vocabulary table to come back whole, and inside the service's own
# ceiling of 4096 pixels a side.
RESOLUTION = 300

# The service measures a page in the pixels of the picture it was sent, and
# everything above it measures one in points -- the unit a text layer is in, and
# the unit its tolerances are written in. A page rendered at RESOLUTION turns
# pixels into points at this rate, so a line is put back in the units the rows
# and columns are worked out in rather than in units of its own.
POINTS = 72 / RESOLUTION

# A page of pictures takes the service a moment; half a minute is a hung service.
TIMEOUT = 30


class OcrError(Exception):
    """The service cannot be reached, or would not read the page.

    Its credentials are missing, its answer is a refusal, or it is not there at
    all -- the three are one kind of trouble to a run: a setup problem the
    learner has to settle, not a lesson the run can carry on past.
    """


def credentials(directory: Path | None = None) -> tuple[str, str]:
    """The service's key and secret, out of the `.env` file in `directory`.

    The file is read where the tool was run from, since that is where its owner
    put it and kept it out of the repository. What is missing is named: a `.env`
    that is not there, and one that is there without both values in it, are the
    two ways this goes wrong and they want different sentences.
    """
    path = (directory or Path.cwd()) / ENV
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise OcrError(
            f"there is no {path} holding {API_KEY} and {SECRET_KEY}, which the OCR "
            "pass needs; write one with the two values from the service's console, "
            "and keep it out of the repository"
        ) from error
    except OSError as error:
        raise OcrError(f"cannot read {path}: {error}") from error
    read = settings(text)
    missing = [name for name in (API_KEY, SECRET_KEY) if not read.get(name)]
    if missing:
        raise OcrError(f"{path} carries no {', '.join(missing)}; the OCR pass needs both")
    return read[API_KEY], read[SECRET_KEY]


class Baidu:
    """The OCR service, as this tool speaks to it."""

    def __init__(self, *, key: str, secret: str, url: str = BASE) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.secret = secret
        self.token: str | None = None

    def read(self, path: Path) -> list[Row]:
        """Every row of a lesson's pages, read back out of its pictures."""
        rows: list[Row] = []
        for number, picture in enumerate(pages(path)):
            rows += page_rows(number, self.words(picture))
        return rows

    def words(self, picture: bytes) -> list[Seen]:
        """The lines one page's picture holds, and where each of them sat.

        The service answers a printed line at a time, which is what a lesson's
        rows are made of -- and where a line is a cell of a vocabulary table,
        which is what its columns are measured by. The characters the answer
        also carries are left alone: asked for, they come back with a table's
        digits and stops split off one by one, and the line is the larger and
        the truer of the two.
        """
        answer = self._call(
            READ, {"access_token": self._token(), "image": base64.b64encode(picture).decode()}
        )
        lines: list[Seen] = []
        for line in answer.get("words_result") or ():
            where, text = line.get("location"), line.get("words")
            if where and text:
                lines.append(
                    Seen(
                        text=text,
                        top=float(where["top"]) * POINTS,
                        x0=float(where["left"]) * POINTS,
                        x1=float(where["left"] + where["width"]) * POINTS,
                    )
                )
        return lines

    def _token(self) -> str:
        """The token a page is posted against, asked for once.

        A run reads a few hundred pages and the service counts a token against
        its own lifetime rather than against a page, so it is asked for on the
        first page and kept for the rest of the run.
        """
        if self.token is None:
            answer = self._call(
                TOKEN,
                {
                    "grant_type": "client_credentials",
                    "client_id": self.key,
                    "client_secret": self.secret,
                },
            )
            token = answer.get("access_token")
            if not token:
                raise OcrError(
                    "the OCR service would not issue a token "
                    f"({answer.get('error_description') or answer.get('error') or 'no token in its answer'}); "
                    "check the key and secret in .env against the service's console"
                )
            self.token = token
        return self.token

    def _call(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        request = Request(
            self.url + path,
            data=urlencode(params).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                answer = json.load(response)
        except (OSError, ValueError) as error:
            raise OcrError(
                f"cannot reach the OCR service at {self.url} ({error}); is there a "
                "connection, and is the address right?"
            ) from error
        if answer.get("error_code"):
            raise OcrError(
                f"the OCR service refused the page: {answer.get('error_msg')} "
                f"({answer['error_code']})"
            )
        return answer


def pages(path: Path) -> list[bytes]:
    """A PDF's pages, as the pictures the service reads.

    A file that cannot be opened is the lesson's problem, reported the way every
    other unreadable lesson is, rather than a traceback out of the renderer.
    """
    try:
        with pdfplumber.open(path) as pdf:
            return [_picture(page) for page in pdf.pages]
    except (OSError, PdfminerException) as error:
        raise LessonError(f"cannot read {path}: {error}") from error


def _picture(page: Any) -> bytes:
    """One rendered page, as a PNG the service will take."""
    buffer = BytesIO()
    page.to_image(resolution=RESOLUTION).original.save(buffer, format="PNG")
    return buffer.getvalue()
