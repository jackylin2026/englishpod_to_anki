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

What comes back is words with coordinates -- the same thing the text layer would
have given -- so a page read this way arrives at the same rows as a page read
out of the text layer, and the lesson above them is read by the same code. The
service is asked for the position of every character and to group English into
words, because a vocabulary table is three columns of text and it is the
geometry of those words that says where one cell ends and the next begins.
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
from pdfplumber.utils.exceptions import PdfminerException

from .layout import Row, Seen, page_rows
from .lesson import LessonError

# Where the service answers, and the two endpoints spoken to.
BASE = "https://aip.baidubce.com"
TOKEN = "/oauth/2.0/token"
READ = "/rest/2.0/ocr/v1/accurate"

# The two values a `.env` file carries, and the file the tool looks for them in.
API_KEY = "BAIDU_OCR_API_KEY"
SECRET_KEY = "BAIDU_OCR_SECRET_KEY"
ENV = ".env"

# A page is rendered at 300 dpi before it is sent: fine enough for the small
# print of a vocabulary table to come back whole, and inside the service's own
# ceiling of 4096 pixels a side.
RESOLUTION = 300

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
    settings = _settings(text)
    missing = [name for name in (API_KEY, SECRET_KEY) if not settings.get(name)]
    if missing:
        raise OcrError(f"{path} carries no {', '.join(missing)}; the OCR pass needs both")
    return settings[API_KEY], settings[SECRET_KEY]


def _settings(text: str) -> dict[str, str]:
    """A `.env` file's settings, as its `NAME=value` lines read them."""
    settings: dict[str, str] = {}
    for line in text.splitlines():
        name, equals, value = line.partition("=")
        if not equals or name.strip().startswith("#"):
            continue
        settings[name.strip()] = value.strip().strip('"').strip("'")
    return settings


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
        """The words one page's picture holds, and where each of them sat."""
        answer = self._call(
            READ,
            {
                "access_token": self._token(),
                "image": base64.b64encode(picture).decode(),
                # Every character positioned, and English grouped into words:
                # which is what a column of a vocabulary table is measured by.
                "recognize_granularity": "small",
                "eng_granularity": "word",
            },
        )
        return [
            Seen(text=text, top=top, x0=left, x1=left + width)
            for line in answer.get("words_result") or ()
            for text, left, top, width in _placed(line)
        ]

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


def _placed(line: Mapping[str, Any]) -> list[tuple[str, float, float, float]]:
    """One line of an answer as words with coordinates.

    A line asked for character positions answers with them, and each is a word
    when English is grouped that way -- which is what the rows are made of. A
    line that answers without them is all that there is of it, so it is taken
    whole rather than dropped.
    """
    located = line.get("chars") or [line]
    placed: list[tuple[str, float, float, float]] = []
    for part in located:
        text = (part.get("char") or part.get("words") or "").strip()
        where = part.get("location") or {}
        if text and where:
            placed.append((text, float(where["left"]), float(where["top"]), float(where["width"])))
    return placed


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
